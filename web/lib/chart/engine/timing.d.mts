import type { Chart, ScoreEvent, LiveNote, InputSnapshot, PlayResult } from '../types';
export const T: Record<string, number>;      // ETiming: TooFast .. TooLate, End = 15
export const J: Record<string, number>;      // EJudgeType
export const K: Record<string, number>;      // EScoreType: Tap Hold Slide Touch Break
export const BOX: { Miss: 0; Good: 1; Great: 2; Perfect: 3; Critical: 4 };
export function convertJudge(timing: number): number;
export const isFast: (timing: number) => boolean;
export const isLate: (timing: number) => boolean;
export const SCORE: number[][];                 // [EScoreType][ETiming] points (NoteScore.judgeScoreTbl)
