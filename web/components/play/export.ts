import { AudioBufferSource, BufferTarget, Mp4OutputFormat, Output, Quality, VideoSample, VideoSampleSource, canEncodeAudio, canEncodeVideo, type EncodedPacket } from "mediabunny";
import type { RenderJob } from "./render.worker";

export const VIDEO_SIZE = 1080;   // the field's own square
export const VIDEO_FPS = 60;      // the game's frame rate
export const AUDIO_RATE = 48000;
const AUDIO = new Quality({ bitrate: 128_000 });
// under Discord's 50 MB upload limit (Nitro Basic) with room for the MP4's index: both browsers' encoders land within a few
// per cent of the bitrate they are given.  Short charts are capped where more bits stop showing
const FILE_BYTES = 47_000_000, MAX_VIDEO_BITRATE = 16_000_000;
const videoQuality = (seconds: number) => new Quality({ bitrate: Math.min(MAX_VIDEO_BITRATE, Math.floor((FILE_BYTES * 8) / seconds) - 128_000), bitrateMode: "variable" });

// H.264 + AAC plays everywhere (Windows, phones, Discord, YouTube).  A browser without an AAC encoder (Firefox) gets FFmpeg's,
// built to WebAssembly, loaded only then since it is a megabyte
export async function canExport(): Promise<boolean> {
  if (typeof VideoEncoder === "undefined" || typeof AudioEncoder === "undefined" || typeof OffscreenCanvas === "undefined") return false;
  if (!(await canEncodeVideo("avc", { width: VIDEO_SIZE, height: VIDEO_SIZE, frameRate: VIDEO_FPS, quality: videoQuality(1) }))) return false;
  const aac = () => canEncodeAudio("aac", { numberOfChannels: 2, sampleRate: AUDIO_RATE, quality: AUDIO });
  if (await aac()) return true;
  (await import("@mediabunny/aac-encoder")).registerAacEncoder();
  return aac();
}

// Firefox's H.264 encoder writes every SPS and PPS into the avcC with its first byte twice, which strict players (Windows,
// iPhones) refuse.  Its keyframes carry the right ones, so the avcC is rebuilt from those; other browsers' is left alone.
function repairAvcC(packet: EncodedPacket, meta?: EncodedVideoChunkMetadata) {
  const config = meta?.decoderConfig, desc = config?.description;
  if (!config || !desc) return;
  const avcC = ArrayBuffer.isView(desc) ? new Uint8Array(desc.buffer, desc.byteOffset, desc.byteLength) : new Uint8Array(desc);
  const len = (avcC[4] & 3) + 1, data = packet.data, sps: Uint8Array[] = [], pps: Uint8Array[] = [];
  for (let o = 0; o + len <= data.length;) {
    let n = 0;
    for (let k = 0; k < len; k++) n = n * 256 + data[o + k];
    const nal = data.subarray(o + len, o + len + n);
    if ((nal[0] & 31) === 7) sps.push(nal); else if ((nal[0] & 31) === 8) pps.push(nal);
    o += len + n;
  }
  const first = avcC.subarray(8, 8 + ((avcC[6] << 8) | avcC[7]));
  if (!sps.length || !pps.length || (first.length === sps[0].length && first.every((b, i) => b === sps[0][i]))) return;
  const out = [1, sps[0][1], sps[0][2], sps[0][3], avcC[4] | 0xfc, 0xe0 | sps.length];
  for (const s of sps) out.push(s.length >> 8, s.length & 255, ...s);
  out.push(pps.length);
  for (const p of pps) out.push(p.length >> 8, p.length & 255, ...p);
  if ([100, 110, 122, 144].includes(sps[0][1])) out.push(0xfd, 0xf8, 0xf8, 0);   // High profile: 4:2:0, 8 bit, as encoded
  config.description = new Uint8Array(out);
}

/** Draw the chart's frames on a few worker threads, encode them in order with the mixed `audio`, and return the MP4; null when aborted. */
export async function encodeVideo(job: Omit<RenderJob, "size" | "fps" | "worker" | "workers">, audio: Promise<AudioBuffer>, progress: (done: number) => void, signal: AbortSignal): Promise<Blob | null> {
  const output = new Output({ format: new Mp4OutputFormat({ fastStart: "in-memory" }), target: new BufferTarget() });
  const video = new VideoSampleSource({ codec: "avc", quality: videoQuality(job.frames / VIDEO_FPS), onEncodedPacket: repairAvcC });
  const sound = new AudioBufferSource({ codec: "aac", quality: AUDIO });
  output.addVideoTrack(video, { frameRate: VIDEO_FPS });
  output.addAudioTrack(sound);
  // drawing a frame on the CPU takes a few times longer than encoding it, so a few threads keep the encoder busy
  const n = Math.max(1, Math.min(6, (navigator.hardwareConcurrency || 4) - 2));
  const drawn = new Map<number, VideoFrame>();
  let wake: (() => void) | null = null, failed: Error | null = null;
  const onAbort = () => wake?.();
  signal.addEventListener("abort", onAbort);
  const workers = Array.from({ length: n }, (_, k) => {
    const w = new Worker(new URL("./render.worker.ts", import.meta.url), { type: "module" });
    w.onmessage = (e: MessageEvent<{ i: number; frame: VideoFrame }>) => { drawn.set(e.data.i, e.data.frame); wake?.(); };
    w.onerror = (e) => { failed = new Error(e.message || "a drawing thread failed"); wake?.(); };
    w.postMessage({ ...job, size: VIDEO_SIZE, fps: VIDEO_FPS, worker: k, workers: n } satisfies RenderJob);
    return w;
  });
  try {
    await output.start();
    for (let i = 0; i < job.frames; i++) {
      while (!drawn.has(i) && !failed && !signal.aborted) await new Promise<void>((r) => { wake = r; });
      if (failed) throw failed;
      if (signal.aborted) { await output.cancel(); return null; }
      const sample = new VideoSample(drawn.get(i)!);
      drawn.delete(i);
      workers[i % n].postMessage(1);
      await video.add(sample);
      sample.close();
      if (i % 15 === 0) progress(i / job.frames);
    }
    await sound.add(await audio);
    await output.finalize();
  } catch (e) {
    if (output.state === "pending" || output.state === "started") await output.cancel();
    throw e;
  } finally {
    signal.removeEventListener("abort", onAbort);
    for (const w of workers) w.terminate();
    for (const f of drawn.values()) f.close();
  }
  return new Blob([output.target.buffer!], { type: "video/mp4" });
}
