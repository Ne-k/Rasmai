// The rating colour bands, from SilentBlue RemyWiki's "maimai DX:Rating". The game's 250-point
// steps inside gold, platinum, rainbow and kiwami are frame variants of one colour, so the table keeps the
// colours and ratingStep the steps. Same table as RATING_BANDS in rasmai/engine/analysis/rating.py; tools/checks/rating.py
// holds the two together. The fills follow the game's frames; ink type reads on every one.
export const RATING_BANDS = [
  { min: 16000, key: "kiwami", fill: "linear-gradient(120deg, #c070f4, #ff6cc8 18%, #ffd23a 36%, #62e070 54%, #3cc8f5 72%, #9a7cff)" },
  { min: 15000, key: "rainbow", fill: "linear-gradient(120deg, #ffa0d2, #ffe07a 20%, #c6f27c 38%, #8ee6f2 58%, #aab8ff 78%, #f0a8f0)" },
  { min: 14500, key: "platinum", fill: "linear-gradient(120deg, #f4de78, #fffbe2 16%, #f9e99a 32%, #fff5c6 60%, #eed266)" },
  { min: 14000, key: "gold", fill: "linear-gradient(120deg, #ffc81a, #fff4a8 16%, #ffd83a 32%, #f7b02a 62%, #ffcf2a)" },
  { min: 13000, key: "silver", fill: "linear-gradient(120deg, #b2d2ef, #e9f5fd 18%, #bcd8f2 34%, #d9ecfa 62%, #a2c4e5)" },
  { min: 12000, key: "bronze", fill: "linear-gradient(90deg, #c0683e, #d47f48 45%, #f0a462)" },
  { min: 10000, key: "purple", fill: "linear-gradient(90deg, #b070ec, #d8a4f6 22%, #d8a4f6 78%, #b070ec)" },
  { min: 7000, key: "red", fill: "linear-gradient(90deg, #e8606c, #f59a9a 22%, #f59a9a 78%, #e8606c)" },
  { min: 4000, key: "yellow", fill: "linear-gradient(90deg, #f0a030, #f9c848 22%, #f9c848 78%, #f0a030)" },
  { min: 2000, key: "green", fill: "linear-gradient(90deg, #7fd045, #a8e864 22%, #a8e864 78%, #7fd045)" },
  { min: 1000, key: "blue", fill: "linear-gradient(90deg, #a4dcfa, #78c6f5 22%, #78c6f5 78%, #a4dcfa)" },
  { min: 0, key: "white", fill: "linear-gradient(90deg, #a9dcf8, #f4fbff 20%, #ffffff 50%, #f4fbff 80%, #a9dcf8)" },
] as const;

export type RatingBand = (typeof RATING_BANDS)[number];

export function ratingBand(rating: number): RatingBand {
  return RATING_BANDS.find((b) => rating >= b.min) ?? RATING_BANDS[RATING_BANDS.length - 1];
}

/** Which 250-point step of gold, platinum, rainbow or kiwami a rating is on, 1 to 4; 0 in the other bands. Same as rating_step. */
export function ratingStep(rating: number): number {
  const band = ratingBand(rating);
  return ["gold", "platinum", "rainbow", "kiwami"].includes(band.key) ? Math.min(4, 1 + Math.floor((rating - band.min) / 250)) : 0;
}

/** The five cells of the plate: the digits, and how many leading ones are only padding. */
export function ratingDigits(rating: number): { digits: string[]; pad: number } {
  const text = String(Math.max(0, Math.min(99999, Math.floor(rating || 0))));
  return { digits: text.padStart(5, "0").split(""), pad: 5 - text.length };
}
