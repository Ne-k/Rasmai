import slideData from "@/lib/chart/slides.json";
import { buildChart } from "@/lib/chart/build.mjs";
import { Field, type FieldOptions, type Sprite } from "./field";
import { advance, sessionAt, NOTE_CLOCK_MS, SIM_FPS, type View } from "./run";
import type { Maidata } from "@/lib/chart/types";

// One of the video export's drawing threads.  Every worker plays the whole chart (cheap) but only draws frames
// worker, worker + workers, ...; each frame goes back to the page as a VideoFrame for the encoder.
export type RenderJob = { maidata: Maidata; slot: number; view: View; colors: FieldOptions["colors"]; frames: number; size: number; fps: number; worker: number; workers: number; skin: Map<string, Sprite> | null };

const AHEAD = 3;   // frames drawn but not yet taken by the encoder; the page sends a 1 for each one it takes
let credit = AHEAD, wake: (() => void) | null = null;

self.onmessage = (e: MessageEvent<RenderJob | number>) => {
  if (typeof e.data === "number") { credit += e.data; wake?.(); }
  else void render(e.data);
};

// RGBA to I420 in BT.709 limited range (what the file is tagged as), done here because Firefox's own conversion shifts the
// colours (white comes out grey); size is even.  One pass over the 2x2 blocks, each pixel read as one little-endian word
function i420(px: Uint8ClampedArray, size: number, out: Uint8Array): Uint8Array {
  const half = size >> 1, cb = size * size, cr = cb + half * half, w = new Uint32Array(px.buffer, px.byteOffset, size * size);
  for (let y = 0, c = 0; y < half; y++) for (let x = 0, i = 2 * y * size; x < half; x++, i += 2, c++) {
    const p0 = w[i], p1 = w[i + 1], p2 = w[i + size], p3 = w[i + size + 1];   // the block's top-left, top-right, bottom-left, bottom-right
    const r0 = p0 & 255, g0 = (p0 >> 8) & 255, b0 = (p0 >> 16) & 255, r1 = p1 & 255, g1 = (p1 >> 8) & 255, b1 = (p1 >> 16) & 255;
    const r2 = p2 & 255, g2 = (p2 >> 8) & 255, b2 = (p2 >> 16) & 255, r3 = p3 & 255, g3 = (p3 >> 8) & 255, b3 = (p3 >> 16) & 255;
    out[i] = (47 * r0 + 157 * g0 + 16 * b0 + 4224) >> 8; out[i + 1] = (47 * r1 + 157 * g1 + 16 * b1 + 4224) >> 8;
    out[i + size] = (47 * r2 + 157 * g2 + 16 * b2 + 4224) >> 8; out[i + size + 1] = (47 * r3 + 157 * g3 + 16 * b3 + 4224) >> 8;
    const r = r0 + r1 + r2 + r3, g = g0 + g1 + g2 + g3, b = b0 + b1 + b2 + b3;
    out[cb + c] = (-26 * r - 86 * g + 112 * b + 131584) >> 10;
    out[cr + c] = (112 * r - 102 * g - 10 * b + 131584) >> 10;
  }
  return out;
}

async function render(job: RenderJob) {
  const cv = new OffscreenCanvas(job.size, job.size);
  // drawn on the CPU: GPU frames reach the encoder at the display's rate.  Opaque, so everything lands on black as the video
  // shows it, and i420 below never sees the full-colour edges of nearly transparent pixels
  const g = cv.getContext("2d", { willReadFrequently: true, alpha: false })!;
  const fld = new Field(cv, slideData), chart = buildChart(job.maidata, job.slot);
  fld.setChart(chart); fld.resize(job.size);
  await fld.loadSkin(job.skin);
  const L = sessionAt(chart, 0), yuv = new Uint8Array(job.size * job.size * 1.5);   // reused: a VideoFrame copies its data
  const per = SIM_FPS / job.fps;   // game frames to each video frame: 1 at 60 fps, 2 at 30
  for (let i = 0, k = 0; i < job.frames; i++) {
    const mine = i % job.workers === job.worker;
    for (; k <= i * per; k++) {
      const now = (k * 1000) / SIM_FPS + NOTE_CLOCK_MS + job.view.offset;
      L.bot.step(now, L.input);
      advance(L, fld, null, now, job.view, job.colors, mine && k === i * per);
    }
    if (!mine) continue;
    while (credit <= 0) await new Promise<void>((r) => { wake = r; });
    credit--;
    // from the pixels, not the canvas, which Chrome can still hand over as a GPU texture
    const frame = new VideoFrame(i420(g.getImageData(0, 0, job.size, job.size).data, job.size, yuv), {
      format: "I420", codedWidth: job.size, codedHeight: job.size, timestamp: Math.round((i * 1e6) / job.fps), duration: Math.round(1e6 / job.fps),
      colorSpace: { primaries: "bt709", transfer: "bt709", matrix: "bt709", fullRange: false },
    });
    self.postMessage({ i, frame }, { transfer: [frame] });
  }
}
