import type { Chart, ScoreEvent, LiveNote, InputSnapshot, PlayResult } from '../types';
export const AREA_NAMES: string[];
export const AREA_COUNT: number;
export const areaIndex: Record<string, number>;
export const laneArea: (group: string, lane: number) => number;
export const isCArea: (i: number) => boolean;
export const FIELD: number;          // 1080
export const LANE_RADIUS: number;    // 480
export const polar: (r: number, thetaDeg: number) => [number, number];
export const laneAngle: (lane: number) => number;
export const SENSOR_CENTERS: [number, number][];
export function sensorAt(x: number, y: number): number;
