import type { CSSProperties } from "react";
import { ratingBand, ratingDigits, ratingStep } from "./band";

export const STAR = "64,13 79.9,47.2 117.3,51.7 89.7,77.3 96.9,114.3 64,96 31.1,114.3 38.3,77.3 10.7,51.7 48.1,47.2";

/** The rating on its plate, as the images draw it: the band's colour, a cell per digit, a star per 250-point step. */
export function RatingPlate({ rating }: { rating: number }) {
  const band = ratingBand(rating);
  const { digits, pad } = ratingDigits(rating);
  const stars = ratingStep(rating);
  return (
    <span className="rplate" style={{ "--band": band.fill } as CSSProperties} role="img"
          aria-label={`rating ${rating}, ${band.key}${stars ? `, step ${stars}` : ""}`}>
      <span className="rp-side" aria-hidden>
        <span className="rp-label">rating</span>
        {stars ? (
          <span className="rp-stars">
            {Array.from({ length: stars }, (_, i) => (
              <svg key={i} viewBox="0 0 128 128"><polygon points={STAR} /></svg>
            ))}
          </span>
        ) : null}
      </span>
      <span className="rp-cells" aria-hidden>
        {digits.map((d, i) => <i key={i} className={i < pad ? "off" : undefined}>{d}</i>)}
      </span>
    </span>
  );
}
