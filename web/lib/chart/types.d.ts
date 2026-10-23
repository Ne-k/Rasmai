// Shared types of the chart engine.  The engine itself is plain JavaScript ported line for line from the game's decompiled
// rules (each .mjs cites the C# it follows); each module's API is declared in the .d.mts file beside it.

export type SlideSeg = { ty: number; f: number; e: number; t0: number; t1: number };
export type Note = {
  k: 'tap' | 'hold' | 'touch' | 'thold' | 'slide';
  t: number;           // ms into the audio
  l: number;           // lane 0-7 (touch: the sensor number within its group, 0-7; C: 0)
  b?: 1; x?: 1; s?: 1; // break, EX, star head
  d?: number;          // hold / touch-hold duration ms
  a?: 'A' | 'B' | 'C' | 'D' | 'E';
  f?: 0 | 1;           // touch firework
  segs?: SlideSeg[];
};
export type Chart = {
  title: string; artist: string; slot: number; name: string; level: string | null; designer: string | null;
  bpm: number | null; endMs: number; notes: Note[]; bars: number[]; warnings: number;
};
export type Maidata = {
  meta: { title: string; artist: string; wholebpm: number | null; first: number };
  charts: Record<number, { slot: number; inote: string; level: string | null; designer: string | null }>;
  fields: Record<string, string>;
};


// ---- engine ----
export type InputSnapshot = { buttonDown: boolean[]; buttonPush: boolean[]; areaDown: boolean[]; areaPush: boolean[] };
/** A live note inside a Session: the chart note plus judgement state. */
export type LiveNote = Note & {
  idx: number; ended: boolean; result: number; diff: number; each?: boolean;
  headResult?: number; headJudged?: boolean; tail?: number; sensor?: number;
  tracker?: { launch: number; arrive: number; index: number; areas: unknown[]; playable: boolean; lastWait: number };
};
export type ScoreEvent = { note: LiveNote; timing: number; diff: number; kind: number; combo: number };

export type PlayResult = {
  song: string; slot: number; title: string; level: string | null; autoplay: boolean; skipped: boolean;
  achievement: number; rank: string; rankId: number; dx: number; dxMax: number; comboType: number; maxCombo: number; theoryCombo: number;
  counts: { critical: number; perfect: number; great: number; good: number; miss: number }; fast: number; late: number; byKind: number[][];
};
