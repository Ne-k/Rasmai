import slideData from "@/lib/chart/slides.json";
import { buildChart } from "@/lib/chart/build.mjs";
import { Field, type FieldOptions } from "./field";
import { advance, sessionAt, NOTE_CLOCK_MS, type View } from "./run";
import type { Maidata } from "@/lib/chart/types";

// One of the video export's drawing threads.  Every worker plays the whole chart (cheap) but only draws frames
// worker, worker + workers, ...; each frame goes back to the page as a VideoFrame for the encoder.
export type RenderJob = { maidata: Maidata; slot: number; view: View; colors: FieldOptions["colors"]; frames: number; size: number; fps: number; worker: number; workers: number };

const AHEAD = 3;   // frames drawn but not yet taken by the encoder; the page sends a 1 for each one it takes
let credit = AHEAD, wake: (() => void) | null = null;

self.onmessage = (e: MessageEvent<RenderJob | number>) => {
  if (typeof e.data === "number") { credit += e.data; wake?.(); }
  else void render(e.data);
};

// RGBA to I420 in BT.709 limited range (what the file is tagged as), done here because Firefox's own conversion shifts the
// colours (white comes out grey); size is even
function i420(px: Uint8ClampedArray, size: number): Uint8Array {
  const half = size >> 1, out = new Uint8Array(size * size * 1.5), cb = size * size, cr = cb + half * half;
  for (let i = 0, p = 0; i < size * size; i++, p += 4) out[i] = (47 * px[p] + 157 * px[p + 1] + 16 * px[p + 2] + 4224) >> 8;
  for (let y = 0; y < half; y++) for (let x = 0; x < half; x++) {
    const p = (2 * y * size + 2 * x) * 4, q = p + size * 4;   // the 2x2 block's top-left and bottom-left pixels
    const r = px[p] + px[p + 4] + px[q] + px[q + 4], g = px[p + 1] + px[p + 5] + px[q + 1] + px[q + 5], b = px[p + 2] + px[p + 6] + px[q + 2] + px[q + 6];
    out[cb + y * half + x] = (-26 * r - 86 * g + 112 * b + 131584) >> 10;
    out[cr + y * half + x] = (112 * r - 102 * g - 10 * b + 131584) >> 10;
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
  await fld.loadSkin("/play/skin");
  const L = sessionAt(chart, 0);
  for (let i = 0; i < job.frames; i++) {
    const now = (i * 1000) / job.fps + NOTE_CLOCK_MS + job.view.offset, mine = i % job.workers === job.worker;
    L.bot.step(now, L.input);
    advance(L, fld, null, now, job.view, job.colors, mine);
    if (!mine) continue;
    while (credit <= 0) await new Promise<void>((r) => { wake = r; });
    credit--;
    // from the pixels, not the canvas, which Chrome can still hand over as a GPU texture
    const frame = new VideoFrame(i420(g.getImageData(0, 0, job.size, job.size).data, job.size), {
      format: "I420", codedWidth: job.size, codedHeight: job.size, timestamp: Math.round((i * 1e6) / job.fps), duration: Math.round(1e6 / job.fps),
      colorSpace: { primaries: "bt709", transfer: "bt709", matrix: "bt709", fullRange: false },
    });
    self.postMessage({ i, frame }, { transfer: [frame] });
  }
}
