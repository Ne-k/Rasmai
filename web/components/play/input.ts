// Pointer (touch / mouse / pen) and keyboard input -> time-stamped sensor and button events for the engine.
// Port of the maimai-dx input.js: every pointer activates the sensor under it and moves between sensors as it drags,
// so slides work with a drag; keys press the lane buttons like the cabinet's eight buttons.
import { sensorAt } from "@/lib/chart/engine/areas.mjs";

export type InputEvent = { perf: number; kind: "area" | "button"; idx: number; on: boolean };

export const DEFAULT_KEYS = ["w", "e", "d", "c", "x", "z", "a", "q"];   // AquaMai's default 1P keys, lane 1..8

type Handler = [EventTarget, string, EventListener];

export class InputController {
  private queue: InputEvent[] = [];
  private pointers = new Map<number, number>();   // pointerId -> sensor index
  private keys = new Map<string, number>();       // key -> lane
  private held = new Set<string>();
  private handlers: Handler[] = [];
  private attached = false;
  onEscape: (() => void) | null = null;

  constructor(private canvas: HTMLCanvasElement, private toField: (cx: number, cy: number) => [number, number]) {
    this.setKeys(DEFAULT_KEYS);
  }

  setKeys(keys: string[]): void {
    this.keys = new Map(keys.map((k, i) => [k.toLowerCase(), i]));
  }

  attach(): void {
    if (this.attached) return;
    const on = <K extends keyof HTMLElementEventMap>(target: HTMLElement, type: K, fn: (e: HTMLElementEventMap[K]) => void) => {
      target.addEventListener(type, fn);
      this.handlers.push([target, type, fn as EventListener]);
    };
    const onWin = <K extends keyof WindowEventMap>(type: K, fn: (e: WindowEventMap[K]) => void) => {
      window.addEventListener(type, fn);
      this.handlers.push([window, type, fn as EventListener]);
    };
    const c = this.canvas;
    const sensor = (e: PointerEvent): number => { const [x, y] = this.toField(e.clientX, e.clientY); return sensorAt(x, y); };
    on(c, "pointerdown", (e) => {
      e.preventDefault();
      try { c.setPointerCapture(e.pointerId); } catch { /* unsupported */ }
      const s = sensor(e);
      this.pointers.set(e.pointerId, s);
      if (s >= 0) this.queue.push({ perf: e.timeStamp, kind: "area", idx: s, on: true });
    });
    on(c, "pointermove", (e) => {
      const prev = this.pointers.get(e.pointerId);
      if (prev === undefined) return;
      e.preventDefault();
      const s = sensor(e);
      if (s === prev) return;
      if (prev >= 0) this.queue.push({ perf: e.timeStamp, kind: "area", idx: prev, on: false });
      if (s >= 0) this.queue.push({ perf: e.timeStamp, kind: "area", idx: s, on: true });
      this.pointers.set(e.pointerId, s);
    });
    const up = (e: PointerEvent) => {
      const prev = this.pointers.get(e.pointerId);
      if (prev === undefined) return;
      this.pointers.delete(e.pointerId);
      if (prev >= 0) this.queue.push({ perf: e.timeStamp, kind: "area", idx: prev, on: false });
    };
    on(c, "pointerup", up); on(c, "pointercancel", up); on(c, "lostpointercapture", up);
    on(c, "contextmenu", (e) => e.preventDefault());
    onWin("keydown", (e) => {
      if (e.repeat) return;
      if (e.key === "Escape") { this.onEscape?.(); return; }
      const k = e.key.toLowerCase(), lane = this.keys.get(k);
      if (lane === undefined || e.ctrlKey || e.metaKey || e.altKey) return;
      e.preventDefault();
      this.held.add(k);
      this.queue.push({ perf: e.timeStamp, kind: "button", idx: lane, on: true });
    });
    onWin("keyup", (e) => {
      const k = e.key.toLowerCase(), lane = this.keys.get(k);
      if (lane === undefined || !this.held.has(k)) return;
      this.held.delete(k);
      this.queue.push({ perf: e.timeStamp, kind: "button", idx: lane, on: false });
    });
    onWin("blur", () => this.releaseAll());
    this.attached = true;
  }

  detach(): void {
    for (const [t, ty, fn] of this.handlers) t.removeEventListener(ty, fn);
    this.handlers = [];
    this.attached = false;
    this.releaseAll();
    this.queue.length = 0;
  }

  releaseAll(): void {
    const now = performance.now();
    for (const s of this.pointers.values()) if (s >= 0) this.queue.push({ perf: now, kind: "area", idx: s, on: false });
    this.pointers.clear();
    for (const k of this.held) {
      const lane = this.keys.get(k);
      if (lane !== undefined) this.queue.push({ perf: now, kind: "button", idx: lane, on: false });
    }
    this.held.clear();
  }

  // time-stamped events since the last drain, sorted by perf
  drain(): InputEvent[] {
    const q = this.queue;
    this.queue = [];
    return q.sort((a, b) => a.perf - b.perf);
  }

  get pushedAreas(): Set<number> {
    const s = new Set<number>();
    for (const v of this.pointers.values()) if (v >= 0) s.add(v);
    return s;
  }
}
