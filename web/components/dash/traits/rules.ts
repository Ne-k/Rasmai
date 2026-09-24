import type { Trait } from "../api";

export const NOT_A_SKILL = new Set(["type", "era", "genre", "designer"]);
export const LEAN = 0.25;
export const LEAN_P = 0.15;
export const CONFIRM_CHARTS = 12;
export const TIER = { basic: "BAS", advanced: "ADV", expert: "EXP", master: "MAS", remaster: "Re:M" } as Record<string, string>;

export const RADAR_MIN = 3;
export const RADAR_FILL = 6;

export type Axis = Trait & { filler?: boolean };
export const isLean = (a: Trait) => Boolean(a.leaning) && !a.verified && a.count >= CONFIRM_CHARTS;
export const isEven = (a: Trait) => !a.verified && !a.leaning && a.count >= CONFIRM_CHARTS && Math.abs(a.offset) < LEAN;
// far enough from your usual score to be worth reading, on enough charts to mean something, and not
// rare enough under shuffled tags to be claimed. These sat in no list at all: not confirmed, not
// leaning, and outside the band "level with the rest" covers.
export const isWatch = (a: Trait) => !a.verified && !isLean(a) && a.count >= CONFIRM_CHARTS && Math.abs(a.offset) >= LEAN;
// how many to show a side, so the tab answers "what should I work on" with something either way
export const BASELINE = 3;

/**
 * The two lists the traits tab shows, as the dashboard and a shared profile both show them.
 *
 * Both are filled from one order, confirmed then leaning then worth watching, so the strongest
 * evidence always leads and the rest is there to give the tab a shape. A confirmed trait is never
 * dropped to make the two sides match: they are levelled up, never down. They are then shown by
 * size, because a list headed by the gap in points reads as broken when the numbers do not run in
 * order.
 *
 * One function for both pages, because two copies of this rule is how a shared profile came to name
 * different traits from the dashboard it was shared from.
 */
export function twoSides(confirmed: Trait[], everything: Trait[]): { weak: Trait[]; strong: Trait[] } {
  // who charted a song and what era it is from are not skills anyone can work on, so they are never
  // named. Filtered here rather than by the caller, because a caller that forgets says a player is
  // good at a charter's name.
  const all = everything.filter((t) => !NOT_A_SKILL.has(t.dimension));
  const seen = new Set<string>();
  const ranked = [...confirmed.filter((t) => !NOT_A_SKILL.has(t.dimension)),
                  ...all.filter(isLean), ...all.filter(isWatch)].filter((t) => {
    const key = `${t.dimension}:${t.label}`;
    return seen.has(key) ? false : (seen.add(key), true);
  });
  const rank = (t: Trait) => (t.verified ? 0 : isLean(t) ? 1 : 2);
  const side = (want: number) =>
    ranked.filter((t) => (want < 0 ? t.offset < 0 : t.offset > 0))
      .sort((a, b) => rank(a) - rank(b) || Math.abs(b.offset) - Math.abs(a.offset));
  const below = side(-1);
  const above = side(1);
  const room = Math.max(BASELINE, below.filter((t) => t.verified).length, above.filter((t) => t.verified).length);
  const bySize = (a: Trait, b: Trait) => Math.abs(b.offset) - Math.abs(a.offset);
  return { weak: below.slice(0, room).sort(bySize), strong: above.slice(0, room).sort(bySize) };
}

/** Pick the axes the wheel is drawn on: confirmed and leaning traits about play, both halves so the shape has contrast.
 *  A wheel with fewer than six is rounded out with the groups the player plays evenly, which sit on the middle ring. */
export function radarAxes(axes: Trait[], limit = 8): Axis[] {
  const pool: Axis[] = axes.filter((a) => (a.verified || isLean(a)) && !NOT_A_SKILL.has(a.dimension));
  if (pool.length < RADAR_FILL) {
    const fillers = axes.filter((a) => isEven(a) && !NOT_A_SKILL.has(a.dimension)).sort((a, b) => Math.abs(b.offset) - Math.abs(a.offset));
    pool.push(...fillers.slice(0, Math.max(0, RADAR_FILL - pool.length)).map((a) => ({ ...a, filler: true })));
    if (pool.length < RADAR_MIN) return [];
  }
  const half = Math.floor(limit / 2);
  const up = pool.filter((a) => a.offset > 0).sort((a, b) => b.offset - a.offset).slice(0, half);
  const down = pool.filter((a) => a.offset < 0).sort((a, b) => a.offset - b.offset).slice(0, limit - half);
  const chosen = [...up, ...down];
  if (chosen.length < limit) {
    const rest = [...pool].sort((a, b) => Math.abs(b.offset) - Math.abs(a.offset)).filter((a) => !chosen.includes(a));
    chosen.push(...rest.slice(0, limit - chosen.length));
  }
  return chosen.sort((a, b) => b.offset - a.offset);
}

/** How many character cells a label takes, counting East Asian characters as two. */


export function odds(p?: number): number {
  return p ? Math.max(1, Math.round(1 / Math.max(p, 0.001))) : 0;
}

export function chance(p?: number): string {
  const n = odds(p);
  return n ? `1 in ${n} shuffles matched it` : "";
}
