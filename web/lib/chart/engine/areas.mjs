// The 34 touch sensors (InputManager.TouchPanelArea order) and their layout.
// Layout numbers come from the game's own TouchPanelMai2.prefab (extract/extract-touch.mjs): all rings share one centre; sensor
// centres sit at radius A 431, B 214, E 310, D 448 (canvas units); A and B at the lane angles (22.5 + 45k degrees clockwise from the
// top), D and E in the gaps (45k degrees); C is the centre, split into a right half (C1) and a left half (C2).

export const AREA_NAMES = [
  ...[1, 2, 3, 4, 5, 6, 7, 8].map((n) => `A${n}`), ...[1, 2, 3, 4, 5, 6, 7, 8].map((n) => `B${n}`), 'C1', 'C2',
  ...[1, 2, 3, 4, 5, 6, 7, 8].map((n) => `D${n}`), ...[1, 2, 3, 4, 5, 6, 7, 8].map((n) => `E${n}`),
];
export const AREA_COUNT = AREA_NAMES.length;                         // 34
export const areaIndex = Object.fromEntries(AREA_NAMES.map((n, i) => [n, i]));
const FIRST = { A: 0, B: 8, D: 18, E: 26 };

// area index of lane `lane` (0-7) in group A/B/D/E; group C ignores the lane
export const laneArea = (group, lane) => (group === 'C' ? areaIndex.C1 : FIRST[group] + (lane & 7));
export const isCArea = (i) => i === areaIndex.C1 || i === areaIndex.C2;

// ConvertTouchPanelRotatePush: a stored area name rotated clockwise by the slide's start lane
export function rotateArea(i, by) {
  if (isCArea(i)) return i;
  const group = AREA_NAMES[i][0];
  return FIRST[group] + (((i - FIRST[group]) + by) % 8);
}

// ---- geometry, in play-field units (the field is 1080 x 1080, centre 0,0, y up; lane buttons sit on a ring of radius 480) ----
export const FIELD = 1080;
export const LANE_RADIUS = 480;
const SCALE = LANE_RADIUS / 431;                                      // sensor canvas units -> field units
const RING = { A: 431, B: 214, D: 448, E: 310 };
const deg = (d) => (d * Math.PI) / 180;
// angle clockwise from the top -> field point
export const polar = (r, thetaDeg) => [r * Math.sin(deg(thetaDeg)), r * Math.cos(deg(thetaDeg))];
export const laneAngle = (lane) => 22.5 + 45 * lane;

export const SENSOR_CENTERS = AREA_NAMES.map((name) => {
  const g = name[0], n = Number(name.slice(1)) - 1;
  if (g === 'C') return [n === 0 ? 55.5 * SCALE : -55.5 * SCALE, 0];
  return polar(RING[g] * SCALE, g === 'A' || g === 'B' ? laneAngle(n) : 45 * n);
});

// which sensor is under a field point (nearest centre), or -1 outside the panel
export function sensorAt(x, y) {
  if (Math.hypot(x, y) > 560) return -1;
  let best = -1, bd = Infinity;
  for (let i = 0; i < AREA_COUNT; i++) {
    const d = (x - SENSOR_CENTERS[i][0]) ** 2 + (y - SENSOR_CENTERS[i][1]) ** 2;
    if (d < bd) { bd = d; best = i; }
  }
  return best;
}
