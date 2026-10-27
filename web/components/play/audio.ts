// One song in a Web Audio context, with a clock the engine can trust.  Ported from the maimai-dx port's audio.js:
// audio ms at performance time p = offsetMs + (p - startPerf) * rate, where startPerf is the performance.now() instant at
// which the sample at offsetMs leaves the speakers (AudioContext.getOutputTimestamp includes the device's output latency).

type Ev = "ended" | "loop";

// one limiter for song + sound effects so a pile of SE cannot clip (port audio.js makeOut); the video export mixes through one too
export function limiter(ctx: BaseAudioContext): DynamicsCompressorNode {
  const out = ctx.createDynamicsCompressor();
  out.threshold.value = -3; out.knee.value = 0; out.ratio.value = 20;
  out.attack.value = 0.002; out.release.value = 0.1;
  return out;
}

export class SongClock {
  private ctx: AudioContext | null = null;
  private gain: GainNode | null = null;
  private out: DynamicsCompressorNode | null = null;
  private buffer: AudioBuffer | null = null;
  private source: AudioBufferSourceNode | null = null;
  private offsetMs = 0;       // song position at startCtx
  private startCtx = 0;       // context time the source was scheduled at
  private startPerf = 0;      // performance.now() when that moment is audible
  private pausedAt = 0;
  private rate = 1;
  private volume = 1;
  private loopA: number | null = null;
  private loopB: number | null = null;
  private listeners: Record<Ev, Set<() => void>> = { ended: new Set(), loop: new Set() };
  playing = false;
  durationMs = 0;

  // the context is created synchronously; only resume() needs the user gesture
  private graph(): { ctx: AudioContext; gain: GainNode; out: DynamicsCompressorNode } {
    if (!this.ctx || !this.gain || !this.out) {
      this.ctx = new AudioContext({ latencyHint: "interactive" });
      this.out = limiter(this.ctx);
      this.out.connect(this.ctx.destination);
      this.gain = this.ctx.createGain();
      this.gain.gain.value = this.volume;
      this.gain.connect(this.out);
    }
    return { ctx: this.ctx, gain: this.gain, out: this.out };
  }

  // built on first access (synchronously; a user gesture is only needed for resume) so effects can decode before a song loads
  get context(): AudioContext | null { return this.graph().ctx; }
  // the node everything audible goes through before the speakers; sound effects connect here
  get output(): AudioNode | null { return this.graph().out; }
  // the decoded song, which the video export mixes again offline
  get song(): AudioBuffer | null { return this.buffer; }

  private async ensure(): Promise<AudioContext> {
    const { ctx } = this.graph();
    if (ctx.state !== "running") await ctx.resume();
    return ctx;
  }

  async load(blob: Blob): Promise<number> {
    const { ctx } = this.graph();
    this.stopSource();
    this.playing = false;
    this.pausedAt = 0;
    this.buffer = await ctx.decodeAudioData(await blob.arrayBuffer());
    this.durationMs = this.buffer.duration * 1000;
    return this.durationMs;
  }

  // performance.now() time at which context time `c` is audible (port audio.js perfAtContext)
  private perfAtContext(ctx: AudioContext, c: number): number {
    const ts = ctx.getOutputTimestamp?.();
    if (ts && ts.performanceTime !== undefined && ts.contextTime !== undefined && ts.performanceTime > 0) {
      return ts.performanceTime + (c - ts.contextTime) * 1000;
    }
    return performance.now() + (c - ctx.currentTime) * 1000 + (ctx.outputLatency || ctx.baseLatency || 0) * 1000;
  }

  async play(fromMs: number = this.pausedAt): Promise<void> {
    const ctx = await this.ensure();
    if (!this.buffer) throw new Error("no song loaded");
    this.stopSource();
    const from = Math.min(Math.max(fromMs, 0), this.durationMs);
    const src = ctx.createBufferSource();
    src.buffer = this.buffer;
    src.playbackRate.value = this.rate;
    src.connect(this.graph().gain);
    // 30 ms of lead so the scheduled start cannot be in the past (port audio.js)
    this.startCtx = ctx.currentTime + 0.03;
    src.start(this.startCtx, from / 1000);
    if (this.loopB !== null && this.loopB > from) src.stop(this.startCtx + (this.loopB - from) / 1000 / this.rate);
    src.onended = () => {
      if (this.source !== src) return;   // stopped by us
      this.source = null;
      this.playing = false;
      if (this.loopA !== null && this.loopB !== null) {
        void this.play(this.loopA);
        this.emit("loop");
      } else {
        this.pausedAt = this.durationMs;
        this.emit("ended");
      }
    };
    this.source = src;
    this.offsetMs = from;
    this.startPerf = this.perfAtContext(ctx, this.startCtx);
    this.playing = true;
  }

  pause(): void {
    if (!this.playing) return;
    this.pausedAt = this.nowMs();
    this.stopSource();
    this.playing = false;
  }

  seek(ms: number): void {
    const to = Math.min(Math.max(ms, 0), this.durationMs);
    if (this.playing) void this.play(to);
    else this.pausedAt = to;
  }

  // re-derive the clock from the audio device so drift cannot build up (eased 5 % per call, never jumps; port audio.js resync)
  nowMs(): number {
    if (!this.playing || !this.ctx) return this.pausedAt;
    const fresh = this.perfAtContext(this.ctx, this.startCtx);
    if (Number.isFinite(fresh)) this.startPerf += (fresh - this.startPerf) * 0.05;
    return Math.max(0, this.offsetMs + (performance.now() - this.startPerf) * this.rate);
  }

  setRate(rate: number): void {
    if (rate === this.rate) return;
    const pos = this.nowMs();
    this.rate = rate;
    if (this.playing) void this.play(pos);   // restart so the linear clock above stays exact
  }

  setLoop(a: number | null, b: number | null): void {
    this.loopA = a;
    this.loopB = b;
    if (this.playing) void this.play(this.nowMs());   // reschedules the stop at b
  }

  setVolume(v: number): void {
    this.volume = v;
    if (this.gain) this.gain.gain.value = v;
  }

  on(event: Ev, fn: () => void): () => void {
    this.listeners[event].add(fn);
    return () => { this.listeners[event].delete(fn); };
  }

  private emit(event: Ev): void {
    for (const fn of this.listeners[event]) fn();
  }

  private stopSource(): void {
    const src = this.source;
    this.source = null;
    try { src?.stop(); } catch { /* already stopped */ }
  }

  close(): void {
    this.stopSource();
    this.playing = false;
    void this.ctx?.close();
    this.ctx = this.gain = this.out = this.buffer = null;
  }
}
