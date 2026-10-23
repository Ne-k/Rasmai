import type { Chart, ScoreEvent, LiveNote, InputSnapshot, PlayResult } from '../types';
import type { Session, InputState } from './play.mjs';
export class AutoPlayer {
  constructor(session: Session, opts?: Record<string, unknown>);
  step(nowMs: number, inp: InputState): void;
}
