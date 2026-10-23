// The game's sound effects (Mai2Cue) and the in-game sound rules of GameSingleCueCtrl.  Port of the maimai-dx sfx.js
// without the voices.  Everything is optional: with no /play/se folder the player is silent apart from the song.
import type { LiveNote, ScoreEvent } from "@/lib/chart/types";
import { convertJudge } from "@/lib/chart/engine/timing.mjs";   // NoteJudge.ConvertJudge: Miss 0, Good 1, Great 2, Perfect 3, Critical 4
import type { SongClock } from "./audio";

export class Sfx {
  private bufs = new Map<string, AudioBuffer>();
  private missing = new Set<string>();
  private loops = new Map<string, AudioBufferSourceNode>();
  master = 1;

  constructor(private clock: SongClock) {}

  private url(name: string): string { return `/play/se/Mai2Cue/${name}.mp3`; }

  async load(name: string): Promise<AudioBuffer | undefined> {
    const url = this.url(name);
    if (this.bufs.has(url) || this.missing.has(url)) return this.bufs.get(url);
    try {
      const r = await fetch(url);
      if (!r.ok) throw new Error(String(r.status));
      const ctx = this.clock.context;
      if (!ctx) throw new Error("no audio context");
      this.bufs.set(url, await ctx.decodeAudioData(await r.arrayBuffer()));
    } catch { this.missing.add(url); }
    return this.bufs.get(url);
  }

  async preload(names: string[]): Promise<void> { await Promise.all(names.map((n) => this.load(n))); }

  // fire and forget; returns the node so a caller can stop it
  private playUrl(url: string, vol: number, loop = false): AudioBufferSourceNode | null {
    const buf = this.bufs.get(url), ctx = this.clock.context, out = this.clock.output;
    if (!buf || !ctx || !out || vol <= 0) return null;
    const src = ctx.createBufferSource(), g = ctx.createGain();
    src.buffer = buf; src.loop = loop; g.gain.value = vol * this.master;
    src.connect(g).connect(out); src.start();
    return src;
  }

  play(name: string, vol = 1): AudioBufferSourceNode | null { return this.playUrl(this.url(name), vol); }

  playLoop(key: string, name: string, vol = 1): void {
    this.stopLoop(key);
    const s = this.playUrl(this.url(name), vol, true);
    if (s) this.loops.set(key, s);
  }

  stopLoop(key: string): void {
    try { this.loops.get(key)?.stop(); } catch { /* already stopped */ }
    this.loops.delete(key);
  }

  stopAll(): void { for (const k of [...this.loops.keys()]) this.stopLoop(k); }
}

// the volume tables of the option menu: OptionVolumeID (0..5 -> 0, .2 .. 1) and OptionVolumeAnswerSoundID (0..10 -> 0 .. 1)
export const VOL5 = [0, 0.2, 0.4, 0.6, 0.8, 1];
export const VOL10 = [0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1];

export const DEFAULT_SE = { ans: 6, tap: 5, brk: 5, ex: 5, slide: 5, brkSlide: 5, touch: 5, touchHold: 5, tapSe: 0, breakSe: 0, exSe: 0, slideSe: 0, critical: 0 };
export type SeConfig = typeof DEFAULT_SE;

// /play/se/seoptions.json
export type SeOption = { name: string; cues: string[]; isDefault?: boolean };
export type SeTable = { tap: SeOption[]; break: SeOption[]; ex: SeOption[]; slide: SeOption[] };

type Family = "tap" | "touch" | "brk" | "ex" | "center" | "brkSlide";

// One per played track.  Feed it what the engine reports each frame; it plays what GameSingleCueCtrl.PlayJudgeSe would.
export class GameSe {
  private c: SeConfig;
  private cue: { tap: string[]; brk: string[]; ex: string; slide: string };
  private answers: number[] = [];
  private slideStarts: { t: number; brk: boolean }[] = [];
  private answerTo = 0;
  private slideTo = 0;

  constructor(private sfx: Sfx, table: SeTable, cfg: Partial<SeConfig> = {}) {
    this.c = { ...DEFAULT_SE, ...cfg };
    const pick = (list: SeOption[], i: number): SeOption => list[i] ?? list[0] ?? { name: "", cues: [] };
    const tapSe = pick(table.tap, this.c.tapSe), brk = pick(table.break, this.c.breakSe);
    this.cue = { tap: tapSe.cues, brk: brk.cues, ex: pick(table.ex, this.c.exSe).cues[0] ?? "", slide: pick(table.slide, this.c.slideSe).cues[0] ?? "" };
  }

  get names(): string[] {
    return ["SE_GAME_ANSWER", ...this.cue.tap, ...this.cue.brk, this.cue.ex, this.cue.slide, "SE_GAME_BREAKSLIDE", "SE_GAME_CHEER", "SE_GAME_CHEER_BREAKSLIDE", "SE_GAME_NORMAL",
      "SE_GAME_SCR_TOUCH_GOOD", "SE_GAME_SCR_TOUCH_GREAT", "SE_GAME_SCR_TOUCH_PERFECT", "SE_GAME_SCR_TOUCH_CENTER",
      "SE_GAME_TOUCH_HOLD_GOOD", "SE_GAME_TOUCH_HOLD_GREAT", "SE_GAME_TOUCH_HOLD_PERFECT", "SE_GAME_TOUCH_HOLD_MISS"].filter(Boolean);
  }

  // the times the game plays the answer sound (GameCtrl: 33 ms after a non-slide note, and after a hold's tail) and the moment a slide star sets off.
  // fromMs: skip everything earlier, so a session rebuilt mid-song does not replay every earlier sound at once
  setNotes(notes: LiveNote[], fromMs = -Infinity): void {
    this.sfx.stopAll();
    this.answers = []; this.slideStarts = [];
    for (const n of notes) {
      if (n.k === "slide") this.slideStarts.push({ t: n.segs?.[0]?.t0 ?? n.t, brk: !!n.b });
      else { this.answers.push(n.t + 33); if (n.k === "hold" || n.k === "thold") this.answers.push((n.tail ?? n.t) + 33); }
    }
    this.answers.sort((a, b) => a - b); this.slideStarts.sort((a, b) => a.t - b.t);
    this.answerTo = this.answers.findIndex((t) => t >= fromMs);
    if (this.answerTo < 0) this.answerTo = this.answers.length;
    this.slideTo = this.slideStarts.findIndex((s) => s.t >= fromMs);
    if (this.slideTo < 0) this.slideTo = this.slideStarts.length;
  }

  // stop looping touch-hold sounds; the page calls this on pause / seek
  stopAll(): void { this.sfx.stopAll(); }

  // events = session.events and heads = session.heads of this frame (already drained by the caller), now = game time in ms
  frame(events: ScoreEvent[], heads: { note: LiveNote; timing: number }[], now: number): void {
    const c = this.c, play = (n: string, v: number) => this.sfx.play(n, v);
    let ans = false, slide = false, brkSlide = false;
    while (this.answerTo < this.answers.length && this.answers[this.answerTo]! <= now) { ans = true; this.answerTo++; }
    while (this.slideTo < this.slideStarts.length && this.slideStarts[this.slideTo]!.t <= now) { if (this.slideStarts[this.slideTo]!.brk) brkSlide = true; else slide = true; this.slideTo++; }
    // highest judgement of each family this frame
    const top: Record<Family, number> = { tap: -1, touch: -1, brk: -1, ex: -1, center: -1, brkSlide: -1 };
    const take = (k: Family, j: number) => { if (j > top[k]) top[k] = j; };
    const addNote = (note: LiveNote, timing: number, head: boolean) => {
      const j = convertJudge(timing);
      if (note.k === "slide") { if (note.b && !head) take("brkSlide", j); return; }
      if (note.k === "touch" || note.k === "thold") {
        if (note.k === "touch") take(note.f ? "center" : "touch", j);
        return;
      }
      if (note.b) take("brk", j); else if (note.x && (note.k === "tap" || head)) take("ex", j); else take("tap", j);
    };
    for (const e of events) addNote(e.note, e.timing, false);
    for (const h of heads) {
      if (h.note.k === "thold") this.touchHold(h.note, h.timing);
      else addNote(h.note, h.timing, true);
    }
    const crit = c.critical, V = (k: "tap" | "brk" | "ex" | "slide" | "brkSlide" | "touch" | "touchHold") => VOL5[c[k]] ?? 0;
    const tapCue = (i: number) => this.cue.tap[i] ?? "";
    if (ans && c.ans > 0) play("SE_GAME_ANSWER", VOL10[c.ans] ?? 0);
    if (top.tap >= 1 && c.tap > 0) {
      const j = top.tap;
      if (crit === 3) { if (j <= 3) play("SE_GAME_NORMAL", V("tap")); }
      else if (!(crit === 2 && j < 4)) play(j === 1 ? tapCue(3) : j === 2 ? tapCue(2) : j === 3 ? tapCue(1) : crit === 0 ? tapCue(1) : tapCue(0), V("tap"));
    }
    if (top.touch >= 1 && c.touch > 0) play(top.touch === 1 ? "SE_GAME_SCR_TOUCH_GOOD" : top.touch === 2 ? "SE_GAME_SCR_TOUCH_GREAT" : "SE_GAME_SCR_TOUCH_PERFECT", V("touch"));
    if (top.center >= 1 && c.touchHold > 0) play("SE_GAME_SCR_TOUCH_CENTER", V("touchHold"));
    if (top.brk >= 1 && c.brk > 0) {
      const j = top.brk;
      if (crit === 3) { if (j <= 3) play("SE_GAME_NORMAL", V("tap")); }
      else if (!(crit === 2 && j < 4)) {
        play((j >= 3 ? this.cue.brk[0] : this.cue.brk[1]) ?? "", V("brk"));
        if (j === 4) play("SE_GAME_CHEER", V("brk"));
      }
    }
    if (top.ex >= 1 && c.ex > 0) play(crit === 3 ? "SE_GAME_NORMAL" : this.cue.ex, crit === 3 ? V("tap") : V("ex"));
    if (slide && c.slide > 0) play(this.cue.slide, V("slide"));
    if (brkSlide) { if (c.brkSlide > 0) play("SE_GAME_BREAKSLIDE", V("brkSlide")); if (c.slide > 0) play(this.cue.slide, V("slide")); }
    if (top.brkSlide === 4 && c.brkSlide > 0 && crit !== 3) play("SE_GAME_CHEER_BREAKSLIDE", V("brkSlide"));
    for (const e of events) if (e.note.k === "thold") this.sfx.stopLoop("touchhold:" + e.note.idx);
  }

  private touchHold(note: LiveNote, timing: number): void {
    if (this.c.touch <= 0) return;
    const j = convertJudge(timing), name = j === 0 ? "SE_GAME_TOUCH_HOLD_MISS" : j === 1 ? "SE_GAME_TOUCH_HOLD_GOOD" : j === 2 ? "SE_GAME_TOUCH_HOLD_GREAT" : "SE_GAME_TOUCH_HOLD_PERFECT";
    this.sfx.playLoop("touchhold:" + note.idx, name, VOL5[this.c.touch] ?? 0);
  }
}
