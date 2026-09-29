// The rating colour bands, from SilentBlue RemyWiki's "maimai DX:Rating". The game's 250-point
// steps inside gold, platinum and rainbow are frame variants of one colour, so the table keeps the
// colours and ratingStep the steps. Same table as RATING_BANDS in rasmai/engine/analysis/rating.py; tools/checks/rating.py
// holds the two together. Ink type reads on every fill; bronze to platinum carry a sheen, rainbow runs corner to corner.
export const RATING_BANDS = [
  { min: 15000, key: "rainbow", fill: "linear-gradient(135deg, #ff3d8f, #ff8a3d 22%, #f0c04a 38%, #6cc57a 56%, #5cd3e8 74%, #b98cf0)" },
  { min: 14500, key: "platinum", fill: "linear-gradient(120deg, #d3f1f6, #ffffff 16%, #a6dce6 30%, #c4ebf1 60%, #8ccbd6)" },
  { min: 14000, key: "gold", fill: "linear-gradient(120deg, #f2c457, #fff1bd 16%, #e3a82a 30%, #f3c85c 60%, #cf9420)" },
  { min: 13000, key: "silver", fill: "linear-gradient(120deg, #cfd2da, #f7f8fa 16%, #a9adba 30%, #d3d6de 60%, #979ba8)" },
  { min: 12000, key: "bronze", fill: "linear-gradient(120deg, #d68a50, #f5c393 16%, #b3672f 30%, #d38f58 60%, #9c5a2a)" },
  { min: 10000, key: "purple", fill: "#b98cf0" },
  { min: 7000, key: "red", fill: "#f0606e" },
  { min: 4000, key: "yellow", fill: "#f5e06a" },
  { min: 2000, key: "green", fill: "#6cc57a" },
  { min: 1000, key: "blue", fill: "#5cd3e8" },
  { min: 0, key: "white", fill: "#f3efe4" },
] as const;

export type RatingBand = (typeof RATING_BANDS)[number];

export function ratingBand(rating: number): RatingBand {
  return RATING_BANDS.find((b) => rating >= b.min) ?? RATING_BANDS[RATING_BANDS.length - 1];
}

/** Which 250-point step of gold, platinum or rainbow a rating is on, 1 to 3; 0 in the other bands. Same as rating_step. */
export function ratingStep(rating: number): number {
  const band = ratingBand(rating);
  return ["gold", "platinum", "rainbow"].includes(band.key) ? Math.min(3, 1 + Math.floor((rating - band.min) / 250)) : 0;
}

/** The five cells of the plate: the digits, and how many leading ones are only padding. */
export function ratingDigits(rating: number): { digits: string[]; pad: number } {
  const text = String(Math.max(0, Math.min(99999, Math.floor(rating || 0))));
  return { digits: text.padStart(5, "0").split(""), pad: 5 - text.length };
}
