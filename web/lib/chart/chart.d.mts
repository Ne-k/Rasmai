import type { Chart, ScoreEvent, LiveNote, InputSnapshot, PlayResult } from 'types';
export const DIFFICULTY_NAMES: string[];
export function parseMaidata(text: string): Maidata;
export function parseLevel(raw: string | null | undefined): { level: number; decimal: number; plus: boolean; musicLevelId: number } | null;
