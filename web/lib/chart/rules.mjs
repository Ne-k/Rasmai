// Pure game-screen rules (no DOM): option tables, note motion (NoteBase / HoldNote / TouchNoteB / SlideRoot), judge-label choice
// (JudgeGrade.Initialize), end-of-track conditions (GameProcess.OnUpdate) and the play result.  Node-testable: test/game.test.mjs.
import { T, J, convertJudge, BOX } from './engine/timing.mjs';
import { clearRank, achieveInt, RANK_NAMES } from './engine/score.mjs';

// ---- option tables (C#/DB/Option*IDEnum.cs) ----
export const NOTE_SPEED = [...Array.from({ length: 37 }, (_, i) => 200 + 25 * i), 5000];                 // OptionNotespeedID values
export const TOUCH_SPEED = [175, 183, 200, 212, 225, 237, 250, 262, 275, 283, 300, 312, 325, 337, 350, 375, 400, 425, 450, 475, 500,
  525, 550, 575, 600, 625, 650, 675, 700, 725, 750, 775, 800, 825, 850, 875, 900, 5000];                  // OptionTouchspeedID values
export const BRIGHTNESS = [0.75, 0.5, 0.4, 0.25, 0];                                                       // OptionMoviebrightnessID (mask alpha)
export const SIZE = [0.7, 1, 1.3];                                                                        // OptionNotesize / OptionSlidesize
// UserOption field -> default enum index (records with isDefault = 1)
export const OPTION_DEFAULTS = {
  NoteSpeed: 14, TouchSpeed: 14, SlideSpeed: 10, AdjustTiming: 20, JudgeTiming: 20, Brightness: 2, TouchEffect: 2, TrackSkip: 0,
  StarRotate: 1, NoteSize: 1, SlideSize: 1, TouchSize: 1, DispCenter: 1, DispChain: 2, OutFrameType: 1, DispJudge: 0, DispJudgePos: 5,
  DispJudgeTouchPos: 1, OutlineDesign: 17, TapDesign: 0, HoldDesign: 0, SlideDesign: 0, StarType: 0, SubmonitorAchive: 0, BarDisp: 0,
  // sound (OptionCateSoundID): enum indices, the same meaning as public/js/sfx.js DEFAULT_SE
  AnsVolume: 6, TapHoldVolume: 5, BreakVolume: 5, ExVolume: 5, SlideVolume: 5, BreakSlideVolume: 5, TouchVolume: 5, TouchHoldVolume: 5,
  TapSe: 0, BreakSe: 0, ExSe: 0, SlideSe: 0, CriticalSe: 0,
};
// UserOption sound fields -> GameSe config keys (sfx.js)
const SE_KEYS = { AnsVolume: 'ans', TapHoldVolume: 'tap', BreakVolume: 'brk', ExVolume: 'ex', SlideVolume: 'slide', BreakSlideVolume: 'brkSlide',
  TouchVolume: 'touch', TouchHoldVolume: 'touchHold', TapSe: 'tapSe', BreakSe: 'breakSe', ExSe: 'exSe', SlideSe: 'slideSe', CriticalSe: 'critical' };
export const RANK_THRESHOLDS = [500000, 600000, 700000, 750000, 800000, 900000, 940000, 970000, 980000, 990000, 995000, 1000000, 1005000];

// app.data.options -> resolved game options.  Accepts the game's UserOption field names (enum indices) and the old site's keys
// (speed/touchSpeed index, judgeB frames, displayA, brightness as a mask alpha).
export function readOptions(o = {}) {
  const r = { ...OPTION_DEFAULTS };
  for (const k of Object.keys(OPTION_DEFAULTS)) if (Number.isFinite(o[k])) r[k] = o[k];
  if (!Number.isFinite(o.NoteSpeed) && Number.isFinite(o.speed)) r.NoteSpeed = o.speed;
  if (!Number.isFinite(o.TouchSpeed) && Number.isFinite(o.touchSpeed)) r.TouchSpeed = o.touchSpeed;
  if (!Number.isFinite(o.AdjustTiming) && Number.isFinite(o.displayA)) r.AdjustTiming = o.displayA;
  const clamp = (v, n) => Math.max(0, Math.min(n - 1, Math.round(v)));
  r.NoteSpeed = clamp(r.NoteSpeed, NOTE_SPEED.length); r.TouchSpeed = clamp(r.TouchSpeed, TOUCH_SPEED.length); r.Brightness = clamp(r.Brightness, 5);
  return {
    ...r,
    noteSpeed: NOTE_SPEED[r.NoteSpeed], touchSpeed: TOUCH_SPEED[r.TouchSpeed],
    adjustMs: ((r.AdjustTiming - 20 + 36) / 10) * 16.666666,                                   // UserOption.GetAdjustMSec
    judgeFrames: Number.isFinite(o.judgeB) && !Number.isFinite(o.JudgeTiming) ? o.judgeB : (r.JudgeTiming - 20) / 10,   // GetJudgeTimingFrame
    maskAlpha: Number.isFinite(o.brightnessAlpha) ? o.brightnessAlpha : BRIGHTNESS[r.Brightness],
    noteSize: SIZE[r.NoteSize] ?? 1, slideSize: SIZE[r.SlideSize] ?? 1,
    // UserOption sound fields win over the older `se` object when both are present
    se: { ...(o.se ?? {}), ...Object.fromEntries(Object.entries(SE_KEYS).filter(([k]) => Number.isFinite(o[k])).map(([k, v]) => [v, o[k]])) },
    // web-only: false = no MV (jacket behind the field) for weak devices; the MV decode + 1080 px draw is the costliest part of a frame
    movie: o.movie !== false,
    // web-only: quick result (default on) — leave 2 s after PlayEnd, or skip the FC/AP effect by a press after 1.5 s; off = the cabinet's wait
    quickResult: o.quickResult !== false,
  };
}

// ---- note motion, ms on the note clock ----
export const START_POS = 120, END_POS = 480;                               // NoteLauncher NoteStart / NoteEnd
export const TOUCH_RADIUS = { A: 400, B: 220, C: 0, D: 410, E: 310 };      // Touch*_Launcher NoteStart y
export const defaultMsec = (speed) => (1000 / (speed / 60)) * 4;           // GameManager.GetNoteSpeedForBeat * 4
const bugAdjust = (speed) => { const s = speed / 150; return (s - 1) * (-0.5 / s) * 1.6 * 1000 / 60; };   // NoteBase.GetMaiBugAdjustMSec

// NoteBase.GetNoteYPosition + NoteCheck scale + NoteGuide scale/alpha.  null before the note exists.
export function tapMotion(t, now, speed) {
  const D = defaultMsec(speed), bug = bugAdjust(speed), start = t - 2 * D - bug;
  if (now < start) return null;
  const sc = now >= start + D ? 1 : Math.max(0, 1 - (start + D - now) / D);
  if (now <= start + D) return { y: START_POS, scale: sc, guide: 0.25, guideA: (now - start) / D, moving: false };
  const p = 1 - (t - now) / D, k = -(1 / 120) * (speed / 150 - 1);
  return { y: START_POS + (END_POS - START_POS) * p + (END_POS - START_POS) * k, scale: sc, guide: 0.25 + 0.75 * p + 0.75 * k, guideA: 1, moving: true };
}

// HoldNote.Execute: head y, body length (along the lane, inward from the head), scale
export function holdMotion(t, tail, now, speed) {
  const m = tapMotion(t, now, speed);
  if (!m) return null;
  const D = defaultMsec(speed), bug = bugAdjust(speed);
  const y = Math.min(m.y, END_POS);
  let len = 0;
  if (m.moving) {
    const t2 = tail - bug;
    if (t2 - D <= now) {
      if (tail > now) len = y - START_POS - (END_POS - START_POS) * (1 - (Math.max(t2, now) - now) / D);
    } else len = y - START_POS;
  }
  return { y, len: Math.max(0, len), scale: m.scale, guide: Math.min(1, m.guide), guideA: m.guideA, tailOn: m.moving && tail - bug - D <= now };
}

// TouchNoteB.GetNoteYPosition: plates fade in for DT/4, then close in on the point with the game's quartic
export function touchMotion(t, now, touchSpeed) {
  const D = defaultMsec(touchSpeed), disp = D * 0.25, start = t - (D + disp);
  if (now <= start) return null;
  if (now <= start + disp) return { plateA: Math.min(1, (now - start) / disp), close: 0, just: false };
  let f = (now - (start + disp)) / D;
  f = 3.5 * f ** 4 - 3.75 * f ** 3 + 1.45 * f ** 2 - 0.05 * f + 0.0005;
  return { plateA: 1, close: Math.min(1, f), just: now >= t };
}

// SlideRoot.UpdateAlpha (arrows) and MoveStarLane (star alpha/scale) before launch
export function slideArrowAlpha(t, now, speed, slideSpeed = 10) {
  const D = defaultMsec(speed), from = t - 2 * D + ((2 * D) / 21) * slideSpeed;
  if (now + 50 >= t) return 1;                                     // IsNoteCheckTimeStartIgnoreJudgeWait (JudgeAdjustMs)
  if (now < from) return 0;
  return t - from < 200 ? 0.5 * (1 - (t - now) / Math.max(1e-6, now - from)) : Math.min(0.5, 0.5 * ((now - from) / 200));
}
export function slideStar(t, launch, now, size = 1) {
  if (now <= t) return { a: 0, scale: 0.75 * size };
  if (now <= launch) { const p = (now - t) / Math.max(1e-6, launch - t); return { a: p, scale: (0.5 + p) * size }; }
  return { a: 1, scale: 1.5 * size };
}

// ---- JudgeGrade.Initialize / InitializeBreak: which labels to show for a judgement ----
// dispJudge = OptionDispjudgeID index (0 Type1A .. 14 Type4E).  -> {main, fastLate, add} sprite names (UI_GAM_<name>) or null = hidden
export function judgeLabels(timing, dispJudge, judgeType, isBreak = false) {
  if (timing === T.TooFast || timing === T.TooLate) return { main: 'Miss' };
  const box = convertJudge(timing), brkType = judgeType === J.Break;
  const FL = timing < T.Critical ? 'Fast' : 'Late';
  const d = dispJudge;
  const inA = d === 0 || d === 5, inB = [1, 4, 6, 9, 11].includes(d), inC = [2, 7, 12].includes(d), inD = [3, 8, 10, 13].includes(d);
  if (box === BOX.Good || box === BOX.Great) {
    const w = box === BOX.Good ? 'Good' : 'Great';
    if (inA) return { main: w };
    if (inB) return { main: w, fastLate: FL };
    if (inC) return { main: FL + w };
    if (inD) return { main: FL };
    return brkType ? { main: FL } : null;                          // 4E
  }
  if (box === BOX.Perfect) {
    if ([0, 1, 2, 5, 6, 7].includes(d)) return { main: 'Perfect' };
    if (d === 4 || d === 9) return brkType ? { main: 'Perfect', fastLate: FL } : { main: 'Perfect' };
    if (d === 11) return { main: 'Perfect', fastLate: FL };
    if (d === 12) return { main: FL + 'Perfect' };
    if (d === 13) return { main: FL };
    if (d === 10 || d === 14) return brkType ? { main: FL } : null;
    return null;                                                   // 1D, 2D
  }
  // Critical
  if ([0, 1, 2, 4].includes(d)) return { main: 'Perfect', add: isBreak ? 'Perfect_Break' : undefined };
  if ([5, 6, 7, 9, 11, 12].includes(d)) return { main: 'Critical', add: isBreak ? 'Critical_Break' : undefined };
  return null;
}

// JudgeGrade@Action.anim (0.25 s): scale 1.3 -> 1 in 5 frames, alpha held then out over the last 5 frames; Add flickers every 2 frames
export function judgeAnim(sec) {
  if (sec < 0 || sec >= 0.25) return null;
  const scale = sec < 0.08333 ? 1.3 - 0.3 * (sec / 0.08333) : 1;
  const alpha = sec < 0.16667 ? 1 : Math.max(0, 1 - (sec - 0.16667) / 0.08333);
  return { scale, alpha, add: Math.floor(sec / 0.033333) % 2 === 1 };
}
// SlideJudge@Action.anim (0.333 s): alpha 0 -> 1 in 5 frames, holds, out in the last 5
export function slideJudgeAnim(sec) {
  if (sec < 0 || sec >= 0.33333) return null;
  return { alpha: sec < 0.08333 ? sec / 0.08333 : sec < 0.25 ? 1 : 1 - (sec - 0.25) / 0.08333, add: Math.floor(sec / 0.033333) % 2 === 1 };
}

// ---- movie mask (GameCtrl.UpdateMovie) ----
export const movieMask = (noteMs, target) => (noteMs <= 0 ? 1 : noteMs < 500 ? 1 + (target - 1) * (noteMs / 500) : target);

// ---- end of track (GameProcess.OnUpdate Play -> PlayEnd -> release check) ----
export const END_WAIT_MS = 6000;
// The game releases only when the song's cue has ended (SoundManager.IsEndMusic), with no fade.  Its cues end soon after the chart:
// over 1431 official charts (A000 ma2 last note end vs the music ACB cue Length) the tail is p50 3.6 s, p90 6.9 s, p95 8.43 s, p99 11.5 s.
// Library audio can run much longer (outros, silence), so the song counts as ended at most this long after the last note — the game's own
// timing for 95 % of its charts — and the rest is faded out with the wipe.
export const OFFICIAL_TAIL_MS = 8430;
export const QUICK_RELEASE_MS = 2000, QUICK_SKIP_MS = 1500, EFFECT_MS = 8000;
// web option quickResult: no effect -> 2 s after PlayEnd; with the FC/AP effect -> its end (8 s), or a tap/button after 1.5 s
export function quickRelease({ sincePlayEnd, effect, pressedAfterSkipable }) {
  if (!effect) return sincePlayEnd >= QUICK_RELEASE_MS;
  return sincePlayEnd >= EFFECT_MS || (sincePlayEnd >= QUICK_SKIP_MS && pressedAfterSkipable);
}
// song time (ms) at which the end-of-track rule treats the music as ended
export const musicEndMs = (audioMs, lastNoteMs) => Math.min(audioMs, lastNoteMs + OFFICIAL_TAIL_MS);
export const TRACK_SKIP_WAIT_MS = 2250;
// state: {allJudged, audioEnded, sincePlayEnd (ms or null), resultEffectEnded, skipAt (ms since skip or null)}
export function canRelease(s) {
  if (s.skipSince !== null && s.skipSince !== undefined && s.skipSince >= TRACK_SKIP_WAIT_MS) return true;
  return s.sincePlayEnd !== null && s.audioEnded && s.resultEffectEnded && s.sincePlayEnd > END_WAIT_MS;
}

// GameResultEffectCtrl.Play: effect prefab, SE, partner voice per combo type (single player never gets sync effects)
export const RESULT_EFFECT = {
  1: { prefab: 'FullCombo', plus: false, se: 'SE_GAME_FULL_COMBO', voice: 'VO_000115' },
  2: { prefab: 'FullCombo', plus: true, se: 'SE_GAME_FULL_COMBO', voice: 'VO_000116' },
  3: { prefab: 'AllPerfect', plus: false, se: 'SE_GAME_ALL_PERFECT', voice: 'VO_000117' },
  4: { prefab: 'AllPerfect', plus: true, se: 'SE_GAME_ALL_PERFECT', voice: 'VO_000118' },
};

// GameAchiveNum (Combo mode): the counter text, right aligned to 5, and the x shift (_intXOffset 26 per missing digit)
export function comboText(combo, intCount = 5, xOffset = 26) {
  const digits = combo > 0 ? Math.floor(Math.log10(combo)) + 1 : 1;
  return { text: String(combo).padStart(5, ' '), x: -(xOffset * (intCount - digits)) };
}
// GameUpperGaugeCtrl.ExecuteAchivement / GameAchiveNum: "%3d.dddd%" from the integer achievement (x10000)
export function achieveText(pct) {
  const a = achieveInt(pct), s = String(a).padStart(7, '0');
  return `${String(Math.floor(a / 10000)).padStart(3, ' ')}.${s.slice(3, 7)}%`;
}
// gauge colour index by clear rank (GameUpperGaugeCtrl.ExecuteLeftGauge)
export const gaugeColorIndex = (rank) => (rank === 0 ? 0 : rank === 1 ? 1 : rank <= 4 ? 2 : rank <= 7 ? 3 : rank <= 11 ? 4 : 5);
export const rankOf = (pct) => clearRank(pct, RANK_THRESHOLDS);

// the play result Game hands to Result (app.data.credit.last)
export function playResult(score, { song, slot, title, level, autoplay = false, skipped = false }) {
  const ach = score.achievement, rank = rankOf(ach);
  return {
    song, slot, title, level, autoplay, skipped,
    achievement: ach, rank: RANK_NAMES[rank], rankId: rank,
    dx: score.dxScore, dxMax: score.dxMax, comboType: score.comboType, maxCombo: score.maxCombo, theoryCombo: score.kinds.length,
    counts: { ...score.counts }, fast: score.fast, late: score.late,
    byKind: score.byKind.map((r) => r.slice()),
  };
}

// grows r (device px, within the square sq) to cover the drawn graphics (+ PAD for Shadow/Outline copies); a particle system anywhere ->
// the whole square.  Returns true when r grew.
const UI_PAD = 16;
export function growUiRect(drawn, v, sq, r) {
  let x0 = Infinity, y0 = Infinity, x1 = -Infinity, y1 = -Infinity;
  for (const n of drawn ?? []) {
    if (n._ps) { x0 = sq.x; y0 = sq.y; x1 = sq.x + sq.w; y1 = sq.y + sq.h; break; }
    if (!(n.image || n.rawImage || n.text || n.counter || n.spriteRenderer)) continue;
    const w = n._world, q = n._rect;
    for (let c = 0; c < 4; c++) {
      const lx = q.x + (c & 1 ? q.w : 0), ly = q.y + (c & 2 ? q.h : 0), wx = w[0] * lx + w[2] * ly + w[4], wy = w[1] * lx + w[3] * ly + w[5];
      const X = v[0] * wx + v[2] * wy + v[4], Y = v[1] * wx + v[3] * wy + v[5];
      if (X < x0) x0 = X; if (X > x1) x1 = X; if (Y < y0) y0 = Y; if (Y > y1) y1 = Y;
    }
  }
  if (!(x1 > x0 && y1 > y0)) return false;
  x0 = Math.max(sq.x, Math.floor(x0 - UI_PAD)); y0 = Math.max(sq.y, Math.floor(y0 - UI_PAD));
  x1 = Math.min(sq.x + sq.w, Math.ceil(x1 + UI_PAD)); y1 = Math.min(sq.y + sq.h, Math.ceil(y1 + UI_PAD));
  if (r.w && r.h && x0 >= r.x && y0 >= r.y && x1 <= r.x + r.w && y1 <= r.y + r.h) return false;
  if (r.w && r.h) { x0 = Math.min(x0, r.x); y0 = Math.min(y0, r.y); x1 = Math.max(x1, r.x + r.w); y1 = Math.max(y1, r.y + r.h); }
  if (x1 <= x0 || y1 <= y0) return false;
  r.x = x0; r.y = y0; r.w = x1 - x0; r.h = y1 - y0;
  return true;
}
