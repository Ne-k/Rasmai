// The play field on a Canvas 2D context: disc, centre readout, rings, buttons, notes, slides, hit effects, judge labels.
// Motion and label choice come from lib/chart/rules.mjs (the game's curves); geometry from engine/areas.mjs.  Field units:
// 1080 square, centre (0,0), y up; lane angles clockwise from the top.  Two looks: the game's own sprites when loadSkin() finds
// public/play/skin (placement maths from maimai-dx public/js/render.js, ppu 1 so 1 px = 1 field unit), else vectors.
import type { Chart, ScoreEvent, LiveNote } from "@/lib/chart/types";
import type { Session } from "@/lib/chart/engine/play.mjs";
import { laneAngle, polar, FIELD, LANE_RADIUS, SENSOR_CENTERS } from "@/lib/chart/engine/areas.mjs";
import { T, J, convertJudge, BOX } from "@/lib/chart/engine/timing.mjs";
import { slideTypeLength } from "@/lib/chart/engine/slides.mjs";
import {
  tapMotion, holdMotion, touchMotion, slideArrowAlpha, slideStar, judgeLabels, judgeAnim, slideJudgeAnim,
  TOUCH_RADIUS, END_POS, defaultMsec,
} from "@/lib/chart/rules.mjs";

export type FieldOptions = {
  noteSpeed: number;      // NOTE_SPEED value (ms table), default 550 (speed 4.5)
  touchSpeed: number;     // default 350
  showSensors: boolean;   // dashed sensor rings A/B/C/D/E and lane markers
  dispJudge: number;      // judgeLabels' dispJudge, default 0
  colors?: { screen: string; ring: string; button: string };   // from the page's theme
  center?: { text: string; label: string } | null;            // the centre readout (combo, achievement...), drawn under everything
  useSkin: boolean;       // the game's sprites when they are loaded (false = the plain vector look)
  outline: number;        // ring design, the game's OptionGameoutline 0..17 (17 = CiRCLE)
  starPink: boolean;      // the game's star type option: pink stars instead of blue
};

const DEFAULTS: FieldOptions = { noteSpeed: 550, touchSpeed: 350, showSensors: false, dispJudge: 0, useSkin: true, outline: 17, starPink: false };
const DEG = Math.PI / 180, TAU = Math.PI * 2, FRAME = 1000 / 60;
const FAN = 13;                                                         // SlideType Fan (engine/slides.mjs)
const FONT = '"Zen Maru Gothic", "Zen Kaku Gothic New", system-ui, sans-serif';
const C = {
  tap: "#ff3f9e", each: "#ffd21e", brk: "#ff8c1a", star: "#2ac8ff", touch: "#4ac4ff",
  exTap: "#ff9ed0", exEach: "#ffe88a", exBrk: "#ffc07a", exStar: "#9ae4ff", glow: "#ffb347",
  screen: "#1d1a2f", ring: "#6a6a7c", button: "#8f8fa3",
  judge: { Critical: "#ffd21e", Perfect: "#ff9a3c", Great: "#ff5c9f", Good: "#4ad66d", Miss: "#9a9ab0", Fast: "#2ac8ff", Late: "#ff3f9e" } as Record<string, string>,
};
// hit effect colours by judgement box (the game's FX_Mai2_Note_Color starts)
const FX: Record<number, string> = { [BOX.Miss]: "#ffffff", [BOX.Good]: "#4ad66d", [BOX.Great]: "#ff5555", [BOX.Perfect]: "#ffd21e", [BOX.Critical]: "#ffd21e" };
// Ex overlay tint (SpriteRenderEx.color): NotesEffectColorTable
const EX_TINT = { tap: "rgb(255,183,232)", each: "rgb(255,245,93)", star: "rgb(0,204,255)", brk: "rgb(255,190,80)" };
const HOLD_PLATES: [string, number, number, number][] = [["touchhold/UI_NOTES_Touch_Hold_01", -30, 30, -135], ["touchhold/UI_NOTES_Touch_Hold_02", -30, -30, -45], ["touchhold/UI_NOTES_Touch_Hold_03", 30, -30, 45], ["touchhold/UI_NOTES_Touch_Hold_04", 30, 30, 135]];
const TAP_PLATES: [number, number, number][] = [[0, 34, 180], [34, 0, 90], [0, -34, 0], [-34, 0, -90]];
const EFFECT_MS = 300, FLASH_MS = 100, HOLD_W = 80, HOLD_CAP = 70;
// SlideFan prefab: row j (0-based) = stripe MM_UI_Game_0{53+j} at y, left copy centred at -w/2, right copy at +w/2 mirrored
const FAN_Y = [429, 354, 286.5, 217.5, 147, 61.5, -25.5, -111, -196.5, -277.5, -373.5];
const FAN_ALPHA = 0.4706;                                                // SlideFan._laneColor alpha
const FAN_TINT = { star: "rgb(0,251,252)", each: "rgb(255,237,37)", brk: "rgb(255,148,77)" };

type Pt = { x: number; y: number; z: number };
type Branch = { pts: Pt[]; total: number; arrows: { x: number; y: number; ang: number }[] };   // ang: radians, maths convention
type Label =
  | { kind: "grade"; x: number; y: number; rot: number; timing: number; jt: number; brk: boolean; born: number }
  | { kind: "slide"; x: number; y: number; rot: number; side: "L" | "R"; timing: number; brk: boolean; born: number };
type Effect = { x: number; y: number; color: string; born: number };
type SlideData = { types?: Record<number, { paths?: Record<number, number[][]> }> } | null | undefined;
type Sprite = { img: CanvasImageSource; w: number; h: number; px: number; py: number; border?: number[] };
type Manifest = Record<string, { w: number; h: number; px: number; py: number; border?: number[] }>;

const rot2 = (x: number, y: number, deg: number): [number, number] => { const a = deg * DEG, c = Math.cos(a), s = Math.sin(a); return [x * c - y * s, x * s + y * c]; };
const touchAngle = (n: LiveNote) => (n.a === "A" || n.a === "B" ? laneAngle(n.l) : n.a === "C" ? 0 : 45 * n.l);
const touchPos = (n: LiveNote): [number, number] => (n.a === "C" ? [0, 0] : polar(TOUCH_RADIUS[n.a ?? "A"] ?? 0, touchAngle(n)));
// BreakNote: EffectSprite alpha = sin(frame * 0.2) * 0.5
const breakPulse = (now: number) => Math.max(0, Math.sin((now / FRAME) * 0.2) * 0.5);
const noteColor = (n: LiveNote) => (n.b ? C.brk : n.each ? C.each : n.k === "slide" || n.s ? C.star : n.k === "touch" || n.k === "thold" ? C.touch : C.tap);
const exColor = (n: LiveNote) => (n.b ? C.exBrk : n.each ? C.exEach : n.s ? C.exStar : C.exTap);
const exTint = (n: LiveNote) => (n.b ? EX_TINT.brk : n.each ? EX_TINT.each : n.s ? EX_TINT.star : EX_TINT.tap);
const loadImage = (src: string) => new Promise<HTMLImageElement>((ok, err) => { const i = new Image(); i.onload = () => ok(i); i.onerror = () => err(new Error(src)); i.src = src; });

// One load per page: every chart's Field shares the sprites, so no chart starts on vectors while 254 images reload.
// A sprite that fails to load is left out rather than failing the whole skin.
let skinPromise: Promise<Map<string, Sprite> | null> | null = null;
export function preloadSkin(base = "/play/skin"): Promise<Map<string, Sprite> | null> {
  skinPromise ??= (async () => {
    try {
      const res = await fetch(`${base}/manifest.json`);
      if (!res.ok) return null;
      const man = (await res.json()) as Manifest;
      const skin = new Map<string, Sprite>();
      await Promise.all(Object.entries(man).map(async ([name, m]) => {
        try { skin.set(name, { ...m, img: await loadImage(`${base}/${name}.png`) }); } catch { /* one missing sprite: the vector fallback covers it */ }
      }));
      return skin.size ? skin : null;
    } catch { return null; }
  })();
  return skinPromise;
}

export class Field {
  private ctx: CanvasRenderingContext2D;
  private dpr = 1; private k = 1; private cx = 0; private cy = 0;      // field -> device px: p = c + k * field (y flipped)
  private chart: Chart | null = null;
  private eachAngle: number[] = []; private double: boolean[] = []; private spin: number[] = []; private slides = new Map<number, Branch[]>();
  private labels: Label[] = []; private effects: Effect[] = []; private flashes: number[] = Array(8).fill(-1e9);
  private session: Session | null = null; private from = 0;
  private loaded: Map<string, Sprite> | null = null; private skin: Map<string, Sprite> | null = null; private tints = new Map<string, HTMLCanvasElement>();
  private outline = 17; private starPink = false;

  constructor(private canvas: HTMLCanvasElement, private slideData: unknown) {
    const ctx = canvas.getContext("2d");
    if (!ctx) throw new Error("canvas 2d context unavailable");
    this.ctx = ctx;
    this.resize();
  }

  // the game's sprites from public/play/skin (not in the public repository): false = keep drawing vectors
  async loadSkin(base = "/play/skin"): Promise<boolean> {
    const skin = await preloadSkin(base);
    this.loaded = skin; this.tints.clear();
    return skin !== null;
  }

  setChart(chart: Chart | null): void {
    this.chart = chart; this.reset(); this.slides.clear(); this.eachAngle = []; this.double = []; this.spin = [];
    if (!chart) return;
    const notes = chart.notes;
    // NoteBase.GetEachAngle: the widest lane offset from the first note of an instant to the others (the EACH guide arc)
    const byT = new Map<number, number[]>();
    notes.forEach((n, i) => { if (n.k === "tap" || n.k === "hold") { const k = Math.round(n.t * 2); (byT.get(k) ?? byT.set(k, []).get(k)!).push(i); } });
    for (const g of byT.values()) {
      if (g.length < 2) continue;
      const head = notes[g[0]]; let ang = 0;
      for (const i of g.slice(1)) { const d = (((notes[i].l - head.l) % 8) + 8) % 8, a = d <= 4 ? 45 * d : -45 * (8 - d); if (Math.abs(a) > Math.abs(ang)) ang = a; }
      this.eachAngle[g[0]] = ang;
    }
    const slideIdx = notes.map((n, i) => i).filter((i) => notes[i].k === "slide");
    for (const i of slideIdx) this.slides.set(i, this.geometry(notes[i].segs ?? []));
    for (let i = 0; i < notes.length; i++) {
      const n = notes[i];
      if (n.k !== "tap" || !n.s) continue;
      const mine = slideIdx.filter((j) => notes[j].l === n.l && Math.abs(notes[j].t - n.t) < 1);
      this.double[i] = mine.length >= 2;
      // StarNote.Initialize: spin = -min(18, (slide length / PI) / duration * 15) degrees per frame
      const s = mine[0] === undefined ? null : notes[mine[0]].segs, g = mine[0] === undefined ? null : this.slides.get(mine[0]);
      if (s && g && s.length) { const dur = s[s.length - 1].t1 - s[0].t0; this.spin[i] = dur > 0 ? -Math.min(18, (g[0].total / Math.PI / dur) * 15) : 0; }
    }
  }

  // slides.json path for each piece, rotated to its start lane (maimai-dx render.js slideGeometry); a fan is three straight branches
  private geometry(segs: NonNullable<Chart["notes"][number]["segs"]>): Branch[] {
    const data = this.slideData as SlideData;
    const first = segs[0];
    if (first && first.ty === FAN) {
      const [x0, y0] = polar(END_POS, laneAngle(first.f));
      return [3, 4, 5].map((k) => { const [x1, y1] = polar(END_POS, laneAngle(first.f + k)); return branchOf(Array.from({ length: 9 }, (_, i) => [x0 + ((x1 - x0) * i) / 8, y0 + ((y1 - y0) * i) / 8] as [number, number])); });
    }
    const raw: [number, number][] = [];
    for (const seg of segs) for (const p of data?.types?.[seg.ty]?.paths?.[slideTypeLength(seg.ty, seg.f, seg.e)] ?? []) raw.push(rot2(p[0], p[1], -45 * seg.f));
    return [branchOf(raw)];
  }

  resize(): void {
    const c = this.canvas, dpr = (this.dpr = window.devicePixelRatio || 1);
    const w = Math.max(1, Math.round(c.clientWidth * dpr)), h = Math.max(1, Math.round(c.clientHeight * dpr));
    if (c.width !== w || c.height !== h) { c.width = w; c.height = h; }
    this.cx = w / 2; this.cy = h / 2; this.k = Math.min(w, h) / FIELD;
  }

  clientToField(clientX: number, clientY: number): [number, number] {
    const r = this.canvas.getBoundingClientRect();
    const px = ((clientX - r.left) / Math.max(1, r.width)) * this.canvas.width, py = ((clientY - r.top) / Math.max(1, r.height)) * this.canvas.height;
    return [(px - this.cx) / this.k, -(py - this.cy) / this.k];
  }

  // ---- events from the page ----
  judged(ev: ScoreEvent, nowMs: number): void {
    const n = ev.note, box = convertJudge(ev.timing), brk = !!n.b;
    if (n.k === "slide") {
      const br = this.slides.get(n.idx)?.[0], last = br?.arrows[br.arrows.length - 1];
      const endLane = (n.segs?.[n.segs.length - 1]?.e ?? 0) & 7, flip = endLane >= 4;
      if (last) this.labels.push({ kind: "slide", x: last.x, y: last.y, rot: last.ang / DEG + (flip ? 180 : 0), side: flip ? "L" : "R", timing: ev.timing, brk, born: nowMs });
      if (box !== BOX.Miss) { const [x, y] = polar(END_POS, laneAngle(endLane)); this.effects.push({ x, y, color: FX[box], born: nowMs }); }
      return;
    }
    if (n.k === "touch" || n.k === "thold") {
      const [x, y] = touchPos(n), rot = n.a === "C" ? 0 : -touchAngle(n), [dx, dy] = rot2(0, -90, rot);   // JudgeTouchGrade._dispPosition[1]
      this.labels.push({ kind: "grade", x: x + dx, y: y + dy, rot, timing: ev.timing, jt: J.Touch, brk: false, born: nowMs });
      if (box !== BOX.Miss) this.effects.push({ x, y, color: FX[box], born: nowMs });
      return;
    }
    const ang = laneAngle(n.l), [x, y] = polar(END_POS, ang), [dx, dy] = rot2(0, -90, -ang);              // JudgeGrade._dispPosition[5]
    const jt = n.x ? J.ExTap : brk ? J.Break : J.Tap;
    this.labels.push({ kind: "grade", x: x + dx, y: y + dy, rot: -ang, timing: ev.timing, jt, brk, born: nowMs });
    if (box !== BOX.Miss) this.effects.push({ x, y, color: n.x && !brk ? FX[BOX.Perfect] : FX[box], born: nowMs });
  }
  headJudged(head: { note: LiveNote; timing: number }, nowMs: number): void {
    const n = head.note, [x, y] = n.k === "thold" ? touchPos(n) : polar(END_POS, laneAngle(n.l));
    this.effects.push({ x, y, color: FX[convertJudge(head.timing)], born: nowMs });
  }
  flash(lane: number, nowMs: number): void { this.flashes[lane & 7] = nowMs; }
  reset(): void { this.labels = []; this.effects = []; this.flashes.fill(-1e9); this.from = 0; }

  // ---- one frame ----
  draw(nowMs: number, session: Session | null, opts: Partial<FieldOptions>): void {
    const o: FieldOptions = { ...DEFAULTS, ...opts }, ctx = this.ctx, c = this.canvas, now = nowMs;
    if (session !== this.session) { this.session = session; this.from = 0; }
    ctx.setTransform(1, 0, 0, 1, 0, 0);
    ctx.clearRect(0, 0, c.width, c.height);
    ctx.setTransform(this.k, 0, 0, -this.k, this.cx, this.cy);
    ctx.lineCap = "round"; ctx.lineJoin = "round";
    const col = o.colors ?? { screen: C.screen, ring: C.ring, button: C.button };
    this.skin = o.useSkin ? this.loaded : null; this.outline = o.outline; this.starPink = o.starPink;

    this.disc(col.screen);
    if (o.center) this.center(o.center.text, o.center.label);
    if (o.showSensors) this.sensors(col.button);
    this.rings(col.ring, col.button, now);
    if (!session) return;

    const notes = session.notes, D = defaultMsec(o.noteSpeed), DT = defaultMsec(o.touchSpeed) * 1.25;
    while (this.from < notes.length && notes[this.from].ended) this.from++;
    const vis: LiveNote[] = [];
    for (let i = this.from; i < notes.length; i++) {
      const n = notes[i];
      if (n.t - Math.max(2 * D + 80, DT + 80) > now) break;
      if (!n.ended) vis.push(n);
    }
    for (const n of vis) if (n.k === "tap" || n.k === "hold") this.guide(n, now, o);
    for (const n of vis) if (n.k === "slide") this.slidePath(n, now, o);
    for (const n of vis) if (n.k === "slide") this.slideStar(n, now);
    // later notes underneath earlier ones (sortingOrder = -NoteIndex*10)
    for (let i = vis.length - 1; i >= 0; i--) if (vis[i].k === "hold") this.hold(vis[i], now, o);
    for (let i = vis.length - 1; i >= 0; i--) if (vis[i].k === "tap") this.tap(vis[i], now, o);
    for (let i = vis.length - 1; i >= 0; i--) if (vis[i].k === "touch" || vis[i].k === "thold") this.touch(vis[i], now, o);
    this.drawEffects(now);
    this.drawLabels(now, o);
  }

  // ---- sprites (render.js spr): pivot at (x, y), rot in degrees counter-clockwise, in the y-up field space ----
  private sprite(name: string) { return this.skin?.get(name) ?? null; }
  private spr(name: string | Sprite, x: number, y: number, s = 1, rot = 0, a = 1, tint: string | null = null, add = false, sx = 1): boolean {
    const sp = typeof name === "string" ? this.sprite(name) : name, ctx = this.ctx;
    if (!sp || a <= 0) return false;
    ctx.save(); ctx.translate(x, y); if (rot) ctx.rotate(rot * DEG); ctx.scale(s * sx, -s);
    ctx.globalAlpha *= a; if (add) ctx.globalCompositeOperation = "lighter";
    ctx.drawImage(tint ? this.tinted(sp, tint) : sp.img, -sp.px * sp.w, -(1 - sp.py) * sp.h, sp.w, sp.h);
    ctx.restore();
    return true;
  }
  private tinted(sp: Sprite, color: string): HTMLCanvasElement {
    const key = `${sp.w}x${sp.h}:${(sp.img as HTMLImageElement).src ?? ""}:${color}`;
    let c = this.tints.get(key);
    if (!c) {
      c = document.createElement("canvas"); c.width = sp.w; c.height = sp.h;
      const g = c.getContext("2d")!;
      g.drawImage(sp.img, 0, 0); g.globalCompositeOperation = "multiply"; g.fillStyle = color; g.fillRect(0, 0, sp.w, sp.h);
      g.globalCompositeOperation = "destination-in"; g.drawImage(sp.img, 0, 0);
      this.tints.set(key, c);
    }
    return c;
  }

  private disc(color: string) {
    const ctx = this.ctx;
    ctx.beginPath(); ctx.arc(0, 0, FIELD / 2, 0, TAU); ctx.fillStyle = color; ctx.fill();
  }
  private sensors(color: string) {
    const ctx = this.ctx;
    ctx.save(); ctx.strokeStyle = color; ctx.globalAlpha = 0.35; ctx.lineWidth = 2; ctx.setLineDash([8, 10]);
    for (const r of [Math.hypot(...SENSOR_CENTERS[8]), Math.hypot(...SENSOR_CENTERS[26]), Math.hypot(...SENSOR_CENTERS[0]), Math.hypot(...SENSOR_CENTERS[18])]) { ctx.beginPath(); ctx.arc(0, 0, r, 0, TAU); ctx.stroke(); }
    ctx.beginPath(); ctx.arc(0, 0, 110, 0, TAU); ctx.stroke();
    for (let i = 0; i < 8; i++) { const [x0, y0] = polar(110, 45 * i), [x1, y1] = polar(FIELD / 2, 45 * i); ctx.beginPath(); ctx.moveTo(x0, y0); ctx.lineTo(x1, y1); ctx.stroke(); }
    ctx.setLineDash([]); ctx.fillStyle = color;
    for (const [x, y] of SENSOR_CENTERS) { ctx.beginPath(); ctx.arc(x, y, 6, 0, TAU); ctx.fill(); }
    ctx.restore();
  }
  // judgement ring + lane buttons: the game's chosen outline design when skinned, else circles; the press flash on top either way
  private rings(ring: string, button: string, now: number) {
    const ctx = this.ctx, outlined = this.spr(`outline/Outline_${String(this.outline).padStart(2, "0")}`, 0, 0);
    if (!outlined) { ctx.beginPath(); ctx.arc(0, 0, END_POS, 0, TAU); ctx.strokeStyle = ring; ctx.lineWidth = 3; ctx.stroke(); }
    ctx.lineWidth = 5; ctx.strokeStyle = button;
    for (let l = 0; l < 8; l++) {
      const [x, y] = polar(LANE_RADIUS, laneAngle(l)), f = (now - this.flashes[l]) / FLASH_MS;
      ctx.beginPath(); ctx.arc(x, y, 42, 0, TAU);
      if (!outlined) ctx.stroke();
      if (f >= 0 && f < 1) { ctx.save(); ctx.globalAlpha = 0.7 * (1 - f); ctx.fillStyle = "#ffffff"; ctx.fill(); ctx.restore(); }
    }
  }

  // NoteGuide: the ring under the note (sprite: guide/* scaled; vector: a short arc); EACH: the arc between the simultaneous notes
  private guide(n: LiveNote, now: number, o: FieldOptions) {
    const m = n.k === "hold" ? holdMotion(n.t, n.tail ?? n.t, now, o.noteSpeed) : tapMotion(n.t, now, o.noteSpeed);
    if (!m || m.guideA <= 0) return;
    const ctx = this.ctx, ang = laneAngle(n.l), each = this.eachAngle[n.idx], moving = "moving" in m ? m.moving : m.tailOn;
    if (this.skin) {
      this.spr(n.b ? "guide/Break" : n.each ? "guide/Each" : n.s ? "guide/Slide" : "guide/Normal", 0, 0, m.guide, -ang, m.guideA);
      if (each && moving) {                                              // NoteEachGuide: EachBar ring cut to the arc between the EACH notes
        const a0 = (90 - ang) * DEG, a1 = a0 - each * DEG;
        ctx.save(); ctx.beginPath(); ctx.moveTo(0, 0); ctx.arc(0, 0, 600 * m.guide, a0, a1, each > 0); ctx.closePath(); ctx.clip();
        this.spr("guide/EachBar", 0, 0, m.guide);
        ctx.restore();
      }
      return;
    }
    const r = LANE_RADIUS * m.guide, a0 = (90 - ang) * DEG;
    ctx.save(); ctx.globalAlpha = 0.25 * m.guideA; ctx.lineWidth = 6; ctx.strokeStyle = "#ffffff";
    ctx.beginPath(); ctx.arc(0, 0, r, a0 - 20 * DEG, a0 + 20 * DEG); ctx.stroke();
    if (each && moving) { ctx.globalAlpha = 0.6 * m.guideA; ctx.strokeStyle = C.each; ctx.beginPath(); ctx.arc(0, 0, r, a0, a0 - each * DEG, each > 0); ctx.stroke(); }
    ctx.restore();
  }

  private tap(n: LiveNote, now: number, o: FieldOptions) {
    const m = tapMotion(n.t, now, o.noteSpeed);
    if (!m || m.scale <= 0) return;
    const ctx = this.ctx, ang = laneAngle(n.l), [x, y] = polar(m.y, ang), s = m.scale;
    if (this.skin) {
      if (n.s) {                                                         // StarNote: spins StarRotateSpeed deg per frame
        const rot = -ang + (this.spin[n.idx] ?? 0) * ((now - (n.t - 2 * defaultMsec(o.noteSpeed))) / FRAME), d = this.double[n.idx] ? "_Double" : "";
        this.spr(n.b ? `breakstar/BreakStar${d}_00` : n.each ? `star/Star_Each${d}_00` : this.starPink ? `star/Star_Pink${d}_00` : `star/Star${d}_00`, x, y, s, rot);
        if (n.b) this.spr(`breakstar/BreakStar${d}_EFF_00`, x, y, s, rot, breakPulse(now), null, true);
        if (n.x) this.spr(n.b ? `breakstar/BreakStar_Ex${d}_00` : `star/Star_Ex${d}_00`, x, y, s, rot, 1, exTint(n));
        return;
      }
      this.spr(n.b ? "break/Break_00" : n.each ? "tap/Tap_Each_00" : "tap/Tap_00", x, y, s, -ang);
      if (n.b) this.spr("break/Break_EFF_00", x, y, s, -ang, breakPulse(now), null, true);
      if (n.x) this.spr(n.b ? "break/Break_Ex_00" : "tap/Tap_Ex_00", x, y, s, -ang, 1, exTint(n));
      return;
    }
    ctx.save(); ctx.translate(x, y); ctx.rotate(-ang * DEG); ctx.scale(s, s);
    if (n.b) this.glow(now, n.s ? 56 : 50);
    if (n.s) {
      if (this.double[n.idx]) { ctx.save(); ctx.rotate(36 * DEG); ctx.globalAlpha = 0.6; this.star(44, noteColor(n)); ctx.restore(); }
      this.star(50, noteColor(n));
      if (n.x) { ctx.strokeStyle = exColor(n); ctx.lineWidth = 6; ctx.stroke(); }
    } else {
      ctx.beginPath(); ctx.arc(0, 0, 44, 0, TAU); ctx.fillStyle = noteColor(n); ctx.fill();
      if (n.x) { ctx.strokeStyle = exColor(n); ctx.lineWidth = 8; ctx.stroke(); }
      ctx.beginPath(); ctx.arc(0, 0, 28, 0, TAU); ctx.strokeStyle = "#ffffff"; ctx.lineWidth = 7; ctx.stroke();
    }
    ctx.restore();
  }
  private star(r: number, color: string) {
    const ctx = this.ctx;
    ctx.beginPath();
    for (let i = 0; i < 10; i++) { const rr = i % 2 ? r * 0.45 : r, a = Math.PI / 2 + (i * Math.PI) / 5; ctx.lineTo(rr * Math.cos(a), rr * Math.sin(a)); }
    ctx.closePath(); ctx.fillStyle = color; ctx.fill();
    ctx.strokeStyle = "#ffffff"; ctx.lineWidth = 4; ctx.stroke();
  }
  // break glow (vector): pulsing warm halo under the note (BreakNote EffectSprite)
  private glow(now: number, r: number) {
    const p = breakPulse(now); if (p <= 0) return;
    const ctx = this.ctx;
    ctx.save(); ctx.globalAlpha = p; ctx.beginPath(); ctx.arc(0, 0, r + 14, 0, TAU); ctx.strokeStyle = C.glow; ctx.lineWidth = 14; ctx.stroke(); ctx.restore();
  }

  // HoldNote: a hexagon with pointed caps (70) of height 140 + body, head at y, body inward, in the lane frame (+y outward)
  private hold(n: LiveNote, now: number, o: FieldOptions) {
    const tail = n.tail ?? n.t, m = holdMotion(n.t, tail, now, o.noteSpeed);
    if (!m || m.scale <= 0) return;
    const ctx = this.ctx, ang = laneAngle(n.l), brk = !!n.b, color = noteColor(n);
    const inWindow = !!n.headJudged && now >= n.t + 100 && now <= tail - 200;   // IsNoteCheckTimeHold{Head,Tail}IgnoreJudgeWait
    // shortcut: draw() gets no input state, so a hold in its window is shown as held (the On skin); upgrade when the page passes pushes
    ctx.save(); ctx.rotate(-ang * DEG);
    if (this.skin) {
      let name = brk ? "breakhold/BreakHold_00" : n.each ? "hold/Hold_Each_00" : "hold/Hold_00";
      if (inWindow) name = brk ? "breakhold/BreakHold_On_00" : n.each ? "hold/Hold_Each_On_00" : "hold/Hold_On_00";
      const sp = this.sprite(name);
      if (sp) {
        // one 9-sliced sprite: caps of `border` (70), body stretched to 140 + len, top = the outer edge
        const draw9 = (sp2: Sprite, alpha = 1, add = false) => {
          const cap = sp2.border?.[3] || 70, w = sp2.w * m.scale, h = (140 + m.len) * m.scale, top = m.y + 70 * m.scale;
          ctx.save(); ctx.globalAlpha *= alpha; if (add) ctx.globalCompositeOperation = "lighter";
          ctx.translate(0, top); ctx.scale(1, -1);                         // y down from the outer edge
          const capH = Math.min(cap * m.scale, h / 2);
          ctx.drawImage(sp2.img, 0, 0, sp2.w, cap, -w / 2, 0, w, capH);
          if (h - 2 * capH > 0) ctx.drawImage(sp2.img, 0, cap, sp2.w, sp2.h - 2 * cap, -w / 2, capH, w, h - 2 * capH);
          ctx.drawImage(sp2.img, 0, sp2.h - cap, sp2.w, cap, -w / 2, h - capH, w, capH);
          ctx.restore();
        };
        draw9(sp);
        if (brk) { const e = this.sprite("breakhold/BreakHold_Eff_00"); if (e) draw9(e, breakPulse(now), true); }
        if (n.x) { const e = this.sprite(brk ? "breakhold/BreakHold_Ex_00" : "hold/Hold_Ex_00"); if (e) draw9({ ...e, img: this.tinted(e, exTint(n)) }); }
        ctx.restore();
        return;
      }
    }
    const h = (140 + m.len) * m.scale, top = m.y + HOLD_CAP * m.scale, w = (HOLD_W * m.scale) / 2, cap = Math.min(HOLD_CAP * m.scale, h / 2);
    ctx.beginPath(); ctx.moveTo(0, top); ctx.lineTo(w, top - cap); ctx.lineTo(w, top - h + cap); ctx.lineTo(0, top - h); ctx.lineTo(-w, top - h + cap); ctx.lineTo(-w, top - cap); ctx.closePath();
    if (brk) { const p = breakPulse(now); if (p > 0) { ctx.save(); ctx.globalAlpha = p; ctx.strokeStyle = C.glow; ctx.lineWidth = 26; ctx.stroke(); ctx.restore(); } }
    ctx.fillStyle = color; ctx.globalAlpha = inWindow ? 0.55 : 0.3; ctx.fill(); ctx.globalAlpha = 1;
    ctx.strokeStyle = n.x ? exColor(n) : color; ctx.lineWidth = 10; ctx.stroke();
    ctx.strokeStyle = "#ffffff"; ctx.lineWidth = 3; ctx.stroke();
    ctx.restore();
  }

  // SlideRoot: chevrons along the path, consumed as the player traces (tracker.progress); alpha from slideArrowAlpha
  private slidePath(n: LiveNote, now: number, o: FieldOptions) {
    const tr = n.tracker, branches = this.slides.get(n.idx);
    if (!tr?.playable || !branches) return;
    const a = slideArrowAlpha(n.t, now, o.noteSpeed);
    if (a <= 0) return;
    const ctx = this.ctx, color = noteColor(n), prog = (tr as unknown as { progress?: number }).progress ?? 0, pulse = n.b ? breakPulse(now) : 0;
    if (this.skin && n.segs?.[0]?.ty === FAN) return this.fan(n, a, prog, pulse);
    const name = n.b ? "breakslide/BreakSlide_00" : n.each ? "slide/Slide_Each_00" : "slide/Slide_00";
    ctx.save(); ctx.globalAlpha = a; ctx.lineWidth = 7;
    for (const br of branches) {
      const hide = Math.floor(prog * br.arrows.length);
      for (let i = hide; i < br.arrows.length; i++) {
        const ar = br.arrows[i];
        if (this.skin) {
          this.spr(name, ar.x, ar.y, 1, ar.ang / DEG - 180);
          if (n.b) this.spr("breakslide/BreakSlide_EFF_00", ar.x, ar.y, 1, ar.ang / DEG - 180, pulse, null, true);
          continue;
        }
        ctx.save(); ctx.translate(ar.x, ar.y); ctx.rotate(ar.ang);
        ctx.beginPath(); ctx.moveTo(-14, 18); ctx.lineTo(6, 0); ctx.lineTo(-14, -18);
        if (pulse > 0) { ctx.save(); ctx.globalAlpha = a * pulse; ctx.strokeStyle = C.glow; ctx.lineWidth = 16; ctx.stroke(); ctx.restore(); }
        ctx.strokeStyle = color; ctx.stroke();
        ctx.restore();
      }
    }
    ctx.restore();
  }
  // SlideFan: eleven stripe rows fanning out from the start lane (root -45·lane, FanTree -22.5), tinted with the lane colour;
  // UpdateAlpha: 0 -> 0.5 over 200 ms, then the colour's own alpha once judging starts; rows vanish as the slide is traced
  private fan(n: LiveNote, alpha: number, prog: number, pulse: number) {
    const ctx = this.ctx, a = alpha >= 1 ? FAN_ALPHA : Math.min(0.5, alpha), tint = n.b ? FAN_TINT.brk : n.each ? FAN_TINT.each : FAN_TINT.star;
    ctx.save(); ctx.globalAlpha = 1; ctx.rotate((-45 * (n.segs?.[0]?.f ?? 0) - 22.5) * DEG);
    const hide = prog * FAN_Y.length;
    for (let j = 0; j < FAN_Y.length; j++) {
      if (j < hide) continue;
      const name = `fan/MM_UI_Game_0${53 + j}`, sp = this.sprite(name); if (!sp) continue;
      const x = sp.w / 2, y = FAN_Y[j];
      this.spr(sp, -x, y, 1, 0, a, tint); this.spr(sp, x, y, 1, 0, a, tint, false, -1);
      if (n.b && pulse > 0) { const e = `fan/SlideFun_Eff_${String(j).padStart(2, "0")}`; this.spr(e, -x, y, 1, 0, pulse * a, null, true); this.spr(e, x, y, 1, 0, pulse * a, null, true, -1); }
    }
    ctx.restore();
  }
  private slideStar(n: LiveNote, now: number) {
    const tr = n.tracker, branches = this.slides.get(n.idx);
    if (!tr?.playable || !branches) return;
    const st = slideStar(n.t, tr.launch, now);
    if (st.a <= 0) return;
    const ctx = this.ctx, f = now <= tr.launch ? 0 : Math.min(1, (now - tr.launch) / Math.max(1, tr.arrive - tr.launch));
    for (const br of branches) {
      const [x, y, dir] = starAt(br, f);
      if (this.skin) { this.spr(n.b ? "breakstar/BreakStar_00" : n.each ? "star/Star_Each_00" : this.starPink ? "star/Star_Pink_00" : "star/Star_00", x, y, st.scale, dir / DEG - 90, st.a); continue; }
      ctx.save(); ctx.globalAlpha = st.a; ctx.translate(x, y); ctx.rotate(dir - Math.PI / 2); ctx.scale(st.scale, st.scale);
      if (n.b) this.glow(now, 40);
      this.star(40, noteColor(n));
      ctx.restore();
    }
  }

  // TouchNoteB / TouchHoldC: four plates closing in on the point, a dot at the point, a gauge arc for touch holds
  private touch(n: LiveNote, now: number, o: FieldOptions) {
    const m = touchMotion(n.t, now, o.touchSpeed);
    if (!m) return;
    const ctx = this.ctx, [x, y] = touchPos(n), color = noteColor(n), hold = n.k === "thold";
    const tail = n.tail ?? n.t, prog = hold ? Math.max(0, Math.min(1, (now - n.t) / Math.max(1, tail - n.t))) : 0;
    ctx.save(); ctx.translate(x, y);
    if (this.skin) {
      if (hold) {
        const gauge = this.sprite("touchhold/UI_NOTES_Touch_Hold_hold");
        if (gauge && prog > 0) {
          ctx.save(); ctx.beginPath(); ctx.moveTo(0, 0); ctx.arc(0, 0, 160, Math.PI / 2, Math.PI / 2 - TAU * prog, true); ctx.closePath(); ctx.clip();
          this.spr(gauge, 0, 0); ctx.restore();
        }
        for (const p of HOLD_PLATES) this.spr(p[0], p[1] * (1 - m.close), p[2] * (1 - m.close), 1, p[3], m.plateA);
        this.spr("touchtap/UI_NOTES_Touch_Point", 0, 0);
      } else {
        const plate = n.each ? "touchtap/UI_NOTES_Touch_Each_01" : "touchtap/UI_NOTES_Touch_01";
        for (const p of TAP_PLATES) this.spr(plate, p[0] * (1 - m.close), p[1] * (1 - m.close), 1, p[2], m.plateA);
        this.spr(n.each ? "touchtap/UI_NOTES_Touch_Each_Point" : "touchtap/UI_NOTES_Touch_Point", 0, 0);
        if (m.just) this.spr("touchtap/UI_NOTES_Touch_Just", 0, 0);
      }
      ctx.restore();
      return;
    }
    const d = 34 + 60 * (1 - m.close);
    if (prog > 0) { ctx.beginPath(); ctx.moveTo(0, 0); ctx.arc(0, 0, 60, Math.PI / 2, Math.PI / 2 - TAU * prog, true); ctx.closePath(); ctx.fillStyle = color; ctx.globalAlpha = 0.35; ctx.fill(); ctx.globalAlpha = 1; }
    ctx.globalAlpha = m.plateA; ctx.fillStyle = color;
    for (let i = 0; i < 4; i++) {
      ctx.save(); ctx.rotate((i * Math.PI) / 2 + (hold ? Math.PI / 4 : 0)); ctx.translate(0, d);
      ctx.beginPath(); ctx.moveTo(0, -22); ctx.lineTo(16, 8); ctx.lineTo(-16, 8); ctx.closePath(); ctx.fill();
      ctx.strokeStyle = "#ffffff"; ctx.lineWidth = 3; ctx.stroke();
      ctx.restore();
    }
    ctx.globalAlpha = 1;
    ctx.beginPath(); ctx.arc(0, 0, m.just ? 14 : 10, 0, TAU); ctx.fillStyle = m.just ? "#ffffff" : color; ctx.fill();
    if (n.f) { ctx.beginPath(); ctx.arc(0, 0, 24, 0, TAU); ctx.strokeStyle = color; ctx.lineWidth = 2; ctx.setLineDash([4, 6]); ctx.stroke(); }
    ctx.restore();
  }

  // a ring bursting out from the judgement point (stands in for the game's particle prefabs in both looks)
  private drawEffects(now: number) {
    const ctx = this.ctx; let k = 0;
    for (const e of this.effects) if (now - e.born < EFFECT_MS && now >= e.born) this.effects[k++] = e;
    this.effects.length = k;
    for (const e of this.effects) {
      const f = (now - e.born) / EFFECT_MS;
      ctx.save(); ctx.globalAlpha = 1 - f; ctx.strokeStyle = e.color; ctx.lineWidth = 12 * (1 - f) + 2;
      ctx.beginPath(); ctx.arc(e.x, e.y, 40 + 90 * f, 0, TAU); ctx.stroke(); ctx.restore();
    }
  }

  private drawLabels(now: number, o: FieldOptions) {
    let k = 0;
    for (const l of this.labels) if (now - l.born < 340 && now >= l.born) this.labels[k++] = l;
    this.labels.length = k;
    for (const l of this.labels) {
      const sec = (now - l.born) / 1000;
      if (l.kind === "slide") {
        const an = slideJudgeAnim(sec); if (!an) continue;
        const box = convertJudge(l.timing), fl = l.timing < T.Critical ? "Fast" : "Late";
        const critShown = judgeLabels(T.Critical, o.dispJudge, J.SlideOut)?.main === "Critical";             // Type1x: no CRITICAL
        const main = box === BOX.Miss ? fl : box === BOX.Critical && critShown ? "Critical" : box >= BOX.Perfect ? "Perfect" : fl + (box === BOX.Great ? "Great" : "Good");
        const flicker = l.brk && box >= BOX.Perfect && an.add;
        if (this.skin) {
          // shortcut: TooFast/TooLate show the plain FAST/LATE sprite and only the Type-1A/2A (_01) variants are used; upgrade with SlideJudge.Initialize's table
          const nm = box === BOX.Good || box === BOX.Great ? `${main}_01` : main;
          this.spr(`slidejudge/UI_GAM_Slide_${l.side}_${nm}`, l.x, l.y, 1, l.rot, an.alpha);
          if (flicker) this.spr(`slidejudge/UI_GAM_Slide_${l.side}_${nm}_Break`, l.x, l.y, 1, l.rot, an.alpha, null, true);
        } else this.text(main, l.x, l.y, l.rot, 36, an.alpha, flicker);
        continue;
      }
      const an = judgeAnim(sec); if (!an) continue;
      const lab = judgeLabels(l.timing, o.dispJudge, l.jt, l.brk); if (!lab) continue;
      const [dx, dy] = rot2(0, -60 * an.scale, l.rot);
      if (this.skin) {
        this.spr(`judge/UI_GAM_${lab.main}`, l.x, l.y, an.scale, l.rot, an.alpha);
        if (lab.add && an.add) this.spr(`judge/UI_GAM_${lab.add}`, l.x, l.y, an.scale, l.rot, an.alpha, null, true);
        if (lab.fastLate) this.spr(`judge/UI_GAM_${lab.fastLate}`, l.x + dx, l.y + dy, an.scale, l.rot, an.alpha);
        continue;
      }
      this.text(lab.main, l.x, l.y, l.rot, 48 * an.scale, an.alpha, !!lab.add && an.add);
      if (lab.fastLate) this.text(lab.fastLate, l.x + dx, l.y + dy, l.rot, 24 * an.scale, an.alpha, false);
    }
  }
  // a judge word ("FastGood" -> "FAST GOOD") coloured by its grade, rotated with the lane (+y outward); flicker = the break Add flash
  private text(word: string, x: number, y: number, rotDeg: number, size: number, alpha: number, flicker: boolean) {
    const ctx = this.ctx, grade = word.replace(/^(Fast|Late)(?=.)/, ""), label = word.replace(/([a-z])([A-Z])/g, "$1 $2").toUpperCase();
    ctx.save(); ctx.translate(x, y); ctx.rotate(rotDeg * DEG); ctx.scale(1, -1);
    ctx.globalAlpha = alpha; ctx.font = `900 ${size}px ${FONT}`; ctx.textAlign = "center"; ctx.textBaseline = "middle";
    ctx.lineWidth = size / 6; ctx.strokeStyle = "rgba(0,0,0,0.6)"; ctx.strokeText(label, 0, 0);
    ctx.fillStyle = flicker ? "#ffffff" : C.judge[grade] ?? "#ffffff"; ctx.fillText(label, 0, 0);
    ctx.restore();
  }
  // the game's centre readout (OptionDispCenter): a number and its caption, under the notes so it never covers one
  private center(text: string, label: string) {
    const ctx = this.ctx;
    ctx.save(); ctx.scale(1, -1); ctx.textAlign = "center"; ctx.textBaseline = "middle"; ctx.fillStyle = "#ffffff";
    ctx.font = `900 ${text.length > 5 ? 96 : 150}px ${FONT}`; ctx.fillText(text, 0, -20);
    ctx.font = `900 36px ${FONT}`; ctx.globalAlpha = 0.8; ctx.fillText(label, 0, 80);
    ctx.restore();
  }
}

function branchOf(raw: [number, number][]): Branch {
  const pts: Pt[] = raw.map(([x, y]) => ({ x, y, z: 0 }));
  let d = 0;
  for (let i = 0; i < pts.length; i++) { if (i) d += Math.hypot(pts[i].x - pts[i - 1].x, pts[i].y - pts[i - 1].y); pts[i].z = d; }
  const arrows = [];
  for (let i = 0; i < pts.length - 1; i++) arrows.push({ x: pts[i].x, y: pts[i].y, ang: Math.atan2(pts[i + 1].y - pts[i].y, pts[i + 1].x - pts[i].x) });
  return { pts, total: d, arrows };
}
// position and heading (rad) at fraction f of a branch
function starAt(g: Branch, f: number): [number, number, number] {
  if (g.pts.length < 2) return [g.pts[0]?.x ?? 0, g.pts[0]?.y ?? 0, 0];
  const target = Math.max(0, Math.min(1, f)) * g.total;
  let i = 1;
  while (i < g.pts.length - 1 && g.pts[i].z < target) i++;
  const a = g.pts[i - 1], b = g.pts[i], k = (target - a.z) / (b.z - a.z || 1);
  return [a.x + (b.x - a.x) * k, a.y + (b.y - a.y) * k, Math.atan2(b.y - a.y, b.x - a.x)];
}
