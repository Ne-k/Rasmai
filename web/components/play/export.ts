import { AudioBufferSource, BufferTarget, EncodedAudioPacketSource, Mp4OutputFormat, NullTarget, Output, Quality, VideoSample, VideoSampleSource, canEncodeAudio, canEncodeVideo, type EncodedPacket } from "mediabunny";
import { preloadSkin, type Sprite } from "./field";
import type { RenderJob } from "./render.worker";

// full: the field's own square at the game's frame rate.  fast: a quarter of the frames' pixels to draw, so about a quarter of the time
export const VIDEO_MODES = { full: { size: 1080, fps: 60, maxBitrate: 16_000_000 }, fast: { size: 720, fps: 30, maxBitrate: 6_000_000 } } as const;
export type VideoMode = keyof typeof VIDEO_MODES;
export const AUDIO_RATE = 48000;
const AUDIO = new Quality({ bitrate: 128_000 });
let audioPieces = 1;
// under Discord's 50 MB upload limit (Nitro Basic) with room for the MP4's index: both browsers' encoders land within a few
// per cent of the bitrate they are given.  Short charts are capped where more bits stop showing
const FILE_BYTES = 47_000_000;
const videoQuality = (seconds: number, mode: VideoMode) =>
  new Quality({ bitrate: Math.min(VIDEO_MODES[mode].maxBitrate, Math.floor((FILE_BYTES * 8) / seconds) - 128_000), bitrateMode: "variable" });

// H.264 + AAC plays everywhere (Windows, phones, Discord, YouTube).  A browser without an AAC encoder (Firefox) gets FFmpeg's,
// built to WebAssembly, loaded only then since it is a megabyte
export async function canExport(mode: VideoMode): Promise<boolean> {
  if (typeof VideoEncoder === "undefined" || typeof AudioEncoder === "undefined" || typeof OffscreenCanvas === "undefined") return false;
  if (!(await canEncodeMode(mode))) return false;
  const aac = () => canEncodeAudio("aac", { numberOfChannels: 2, sampleRate: AUDIO_RATE, quality: AUDIO });
  if (await aac()) return true;
  (await import("@mediabunny/aac-encoder")).registerAacEncoder();
  audioPieces = 4;
  return aac();
}

// a browser's first look at its H.264 encoder takes over a second in Chrome, so the player asks as it opens and Export finds it answered
const videoChecks = new Map<VideoMode, Promise<boolean>>();
export function canEncodeMode(mode: VideoMode): Promise<boolean> {
  const { size, fps } = VIDEO_MODES[mode];
  let check = videoChecks.get(mode);
  if (!check) videoChecks.set(mode, (check = canEncodeVideo("avc", { width: size, height: size, frameRate: fps, quality: videoQuality(1, mode) })));
  return check;
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

const AAC_FRAME = 1024, AAC_LEAD = 4 * AAC_FRAME;
// FFmpeg's encoder takes about a quarter of the song's length on one thread, and each encoder gets a thread of its own.  Each piece
// starts and ends a few frames past the samples it keeps, so the encoder has settled by its seam, and is cut on a frame
async function encodeAudioPieces(buf: AudioBuffer, track: EncodedAudioPacketSource, pieces: number): Promise<void> {
  const step = Math.ceil(buf.length / pieces / AAC_FRAME) * AAC_FRAME, rate = buf.sampleRate;
  const parts = await Promise.all(Array.from({ length: pieces }, async (_, k) => {
    const lo = k * step, hi = Math.min(buf.length, lo + step);
    const kept: [EncodedPacket, EncodedAudioChunkMetadata | undefined][] = [];
    if (lo >= hi) return kept;
    const from = Math.max(0, lo - AAC_LEAD), to = Math.min(buf.length, hi + AAC_LEAD);
    const piece = new AudioBuffer({ length: to - from, numberOfChannels: buf.numberOfChannels, sampleRate: rate });
    for (let c = 0; c < buf.numberOfChannels; c++) piece.copyToChannel(buf.getChannelData(c).subarray(from, to), c);
    const output = new Output({ format: new Mp4OutputFormat(), target: new NullTarget() });
    const source = new AudioBufferSource({ codec: "aac", quality: AUDIO, onEncodedPacket: (p, meta) => {
      const at = from + Math.round(p.timestamp * rate);
      if (at >= lo && (at < hi || hi === buf.length)) kept.push([p.clone({ timestamp: at / rate }), meta]);
    } });
    output.addAudioTrack(source);
    await output.start();
    await source.add(piece);
    await output.finalize();
    return kept;
  }));
  const packets = parts.flat();
  for (const [i, [p]] of packets.entries()) await track.add(p, i === 0 ? packets[0][1] : undefined);
}

/** Draw the chart's frames on a few worker threads, encode them in order with the mixed `audio`, and return the MP4; null when aborted. */
export async function encodeVideo(job: Omit<RenderJob, "size" | "fps" | "worker" | "workers" | "skin">, mode: VideoMode, audio: Promise<AudioBuffer>, progress: (done: number) => void, signal: AbortSignal): Promise<Blob | null> {
  const { size, fps } = VIDEO_MODES[mode];
  const output = new Output({ format: new Mp4OutputFormat({ fastStart: "in-memory" }), target: new BufferTarget() });
  const video = new VideoSampleSource({ codec: "avc", quality: videoQuality(job.frames / fps, mode), onEncodedPacket: repairAvcC });
  const pieces = audioPieces;
  const sound = pieces > 1 ? new EncodedAudioPacketSource("aac") : new AudioBufferSource({ codec: "aac", quality: AUDIO });
  output.addVideoTrack(video, { frameRate: fps });
  output.addAudioTrack(sound);
  // drawing a frame on the CPU takes a few times longer than encoding it, so a few threads keep the encoder busy
  const n = Math.max(1, Math.min(6, (navigator.hardwareConcurrency || 4) - 2));
  // copies of the page's decoded sprites, moved to each thread: decoding its own took each one seconds before the first frame
  const skin = await preloadSkin();
  const copy = async ([name, s]: [string, Sprite]): Promise<[string, Sprite]> => [name, { ...s, img: await createImageBitmap(s.img) }];
  const skins = await Promise.all(Array.from({ length: n }, async () => skin && new Map(await Promise.all([...skin].map(copy)))));
  const drawn = new Map<number, VideoFrame>();
  let wake: (() => void) | null = null, failed: Error | null = null;
  const onAbort = () => wake?.();
  signal.addEventListener("abort", onAbort);
  const workers = Array.from({ length: n }, (_, k) => {
    const w = new Worker(new URL("./render.worker.ts", import.meta.url), { type: "module" });
    w.onmessage = (e: MessageEvent<{ i: number; frame: VideoFrame }>) => { drawn.set(e.data.i, e.data.frame); wake?.(); };
    w.onerror = (e) => { failed = new Error(e.message || "a drawing thread failed"); wake?.(); };
    const own = skins[k];
    w.postMessage({ ...job, size, fps, worker: k, workers: n, skin: own } satisfies RenderJob, own ? [...own.values()].map((s) => s.img as ImageBitmap) : []);
    return w;
  });
  try {
    await output.start();
    // encoded alongside the frames: Firefox's WebAssembly AAC encoder takes about a third of the song's length on its own
    const sounded = audio.then((buf) => sound instanceof AudioBufferSource ? sound.add(buf) : encodeAudioPieces(buf, sound, pieces));
    sounded.catch(() => {});   // awaited below; this only keeps an abort from leaving it unhandled
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
    await sounded;
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
