import type { Chart, ScoreEvent, LiveNote, InputSnapshot, PlayResult } from '../types';
export class Session {
  constructor(chart: Chart, slideData: unknown, opts?: { judgeFrames?: number; adjustMs?: number });
  notes: LiveNote[]; live: LiveNote[]; events: ScoreEvent[]; heads: { note: LiveNote; timing: number }[];
  score: ScoreKeeper; chartEnd: number; adjustMs: number;
  tick(nowMs: number, inp: InputSnapshot): ScoreKeeper;
}
export class InputState {
  buttonPush: boolean[]; areaPush: boolean[]; buttonDown: boolean[]; areaDown: boolean[];
  setButton(i: number, on: boolean): void;
  setArea(i: number, on: boolean): void;
  snapshot(): InputSnapshot;
}
