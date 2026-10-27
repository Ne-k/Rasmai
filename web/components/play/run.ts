import slideData from "@/lib/chart/slides.json";
import { Session, InputState } from "@/lib/chart/engine/play.mjs";
import { AutoPlayer } from "@/lib/chart/engine/bot.mjs";
import { K, T, SCORE } from "@/lib/chart/engine/timing.mjs";
import { achieveText } from "@/lib/chart/rules.mjs";
import type { Chart } from "@/lib/chart/types";
import type { Field, FieldOptions } from "./field";
import type { GameSe } from "./sfx";

export type Center = "off" | "combo" | "achievement" | "achievementDown" | "dx";
export type View = Omit<FieldOptions, "colors" | "center"> & { center: Center; offset: number; rate: number };

// The note clock runs 110 ms ahead of the audio: the game's Normal timing adjust (+60 ms on every note) plus the 50 ms its
// judgement windows are centred after the note (maimai-dx docs/game.md); the engine's Session adds the 60 itself.
export const NOTE_CLOCK_MS = 110;
export const TICK_MS = 8;          // fast-forward step when a session is rebuilt at a position
export const SIM_FPS = 60;         // the game's own rate: a video exported at fewer frames still plays the chart at this, so auto play and its sounds land as live

/** Points lost so far against an all-Critical play: base points and break bonus, as the game's counting-down achievement needs. */
export function lostSoFar(events: { kind: number; timing: number }[]) {
  let score = 0, bonus = 0;
  for (const e of events) { score += SCORE[e.kind][T.Critical] - SCORE[e.kind][e.timing]; if (e.kind === K.Break) bonus += SCORE[K.BreakBonus][T.Critical] - SCORE[K.BreakBonus][e.timing]; }
  return { score, bonus };
}

/** A fresh session with everything before `audioMs` already played by the perfect player. */
export function sessionAt(chart: Chart, audioMs: number) {
  const session = new Session(chart, slideData, { judgeFrames: 0, adjustMs: 60 });
  const input = new InputState();
  const bot = new AutoPlayer(session);
  const until = audioMs + NOTE_CLOCK_MS;
  for (let t = -600; t < until; t += TICK_MS) { bot.step(t, input); session.tick(t, input.snapshot()); }
  return { session, input, bot, eventCursor: session.events.length, headCursor: session.heads.length, lost: lostSoFar(session.events) };
}

export type Live = ReturnType<typeof sessionAt>;

// the game's centre readout: combo, achievement counting up from 0 or down from the theoretical maximum, or the DX score
function centerText(mode: Center, L: Live) {
  const sc = L.session.score;
  if (mode === "combo") return sc.combo > 0 ? { text: String(sc.combo), label: "COMBO" } : null;
  if (mode === "achievement") return { text: achieveText(sc.achievement).trim(), label: "ACHIEVEMENT" };
  if (mode === "achievementDown") {
    const top = sc.breakBonusTotal ? 101 : 100;
    const down = top - (sc.allPerfect ? (L.lost.score / sc.allPerfect) * 100 : 0) - (sc.breakBonusTotal ? L.lost.bonus / sc.breakBonusTotal : 0);
    return { text: achieveText(Math.max(0, down)).trim(), label: "ACHIEVEMENT" };
  }
  if (mode === "dx") return { text: String(sc.dxScore), label: "DX SCORE" };
  return null;
}

/** Judge a session up to `now`, hand its new judgements to the field and the sound effects, and draw the frame when `draw`. */
export function advance(L: Live, fld: Field | null, se: GameSe | null | undefined, now: number, o: View, colors: FieldOptions["colors"], draw = true) {
  L.session.tick(now, L.input.snapshot());
  const newEvents = L.session.events.slice(L.eventCursor), newHeads = L.session.heads.slice(L.headCursor);
  for (const ev of newEvents) fld?.judged(ev, now);
  for (const h of newHeads) fld?.headJudged(h, now);
  L.eventCursor = L.session.events.length; L.headCursor = L.session.heads.length;
  se?.frame(newEvents, newHeads, now);
  if (newEvents.length) { const more = lostSoFar(newEvents); L.lost.score += more.score; L.lost.bonus += more.bonus; }
  if (draw) fld?.draw(now, L.session, { ...o, colors, center: centerText(o.center, L) });
}
