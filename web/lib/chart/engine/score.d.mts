import type { Chart, ScoreEvent, LiveNote, InputSnapshot, PlayResult } from '../types';
export class ScoreKeeper {
  kinds: number[]; combo: number; maxCombo: number; judged: number; fast: number; late: number;
  counts: { critical: number; perfect: number; great: number; good: number; miss: number };
  byKind: number[][];
  allPerfect: number; breakBonusTotal: number;   // the chart's base-point and break-bonus maximums
  readonly done: boolean; readonly achievement: number; readonly dxScore: number; readonly dxMax: number; readonly comboType: number;
}
export const COMBO_NAMES: string[];
export const RANK_NAMES: string[];
export function achieveInt(pct: number): number;
export function clearRank(pct: number, thresholds: number[]): number;
export function singleRate(levelTimes10: number, achievementPct: number, comboType: number): number;
