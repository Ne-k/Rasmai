import { useEffect, useRef, useState } from "react";
import { type ChartDetail } from "./api";
import { Empty, pct } from "./bits";
import { RANK_LINES } from "./Detail";

export function ScoreHistory({ points }: { points: ChartDetail["history"] }) {
  const box = useRef<HTMLDivElement>(null);
  const [width, setWidth] = useState(640);
  useEffect(() => {
    const el = box.current;
    if (!el || typeof ResizeObserver === "undefined") return;
    const watch = new ResizeObserver((entries) => {
      const w = Math.round(entries[0]?.contentRect.width ?? 0);
      if (w > 0) setWidth(Math.max(240, w));
    });
    watch.observe(el);
    return () => watch.disconnect();
  }, []);
  const sorted = [...points].sort((a, b) => a.when.localeCompare(b.when));
  if (sorted.length < 2) {
    return (
      <div className="score-history" ref={box}>
        <Empty>
          {sorted.length === 1
            ? `One point so far: ${pct(sorted[0].achievement, 4)} on ${new Date(sorted[0].when).toLocaleDateString()}.`
            : "No stored scores for this chart yet."}{" "}
          Every read records the plays it sees, so this fills in as you play it.
        </Empty>
      </div>
    );
  }
  const W = width;
  const H = width < 480 ? 150 : 180;
  const padL = 44;
  const padR = 12;
  const padT = 12;
  const padB = 24;
  const values = sorted.map((p) => p.achievement);
  const t0 = new Date(sorted[0].when).getTime();
  const t1 = Math.max(new Date(sorted[sorted.length - 1].when).getTime(), t0 + 1);
  let lo = Math.min(...values) - 0.4;
  let hi = Math.max(...values) + 0.4;
  if (hi - lo < 1.5) {
    const mid = (hi + lo) / 2;
    lo = mid - 0.75;
    hi = mid + 0.75;
  }
  // the first read seeds every chart at one moment, so points sharing a timestamp are laid out
  // evenly by their order instead of stacking on top of each other at the left edge
  const spread = t1 - t0 < 10 * 60 * 1000;
  const x = (t: number, i: number) =>
    padL + (spread ? i / (sorted.length - 1) : (t - t0) / (t1 - t0)) * (W - padL - padR);
  const y = (v: number) => padT + ((hi - v) / (hi - lo)) * (H - padT - padB);
  let best = 0;
  const steps: string[] = [];
  const bests: number[] = [];
  sorted.forEach((p, i) => {
    const at = x(new Date(p.when).getTime(), i);
    if (p.achievement > best) {
      if (i > 0) steps.push(`L${at.toFixed(1)} ${y(best).toFixed(1)}`);
      best = p.achievement;
      bests.push(i);
    }
    steps.push(`${i === 0 ? "M" : "L"}${at.toFixed(1)} ${y(best).toFixed(1)}`);
  });
  // only label the ranks that have room: a wide range crams SSS, SS+, SS and S+ into a few pixels
  const drawn: number[] = [];
  const ranks = RANK_LINES.filter(([, v]) => v > lo && v < hi).filter(([, v]) => {
    const at = y(v);
    if (drawn.some((other) => Math.abs(other - at) < 13)) return false;
    drawn.push(at);
    return true;
  });
  const room = (at: number) => !drawn.some((other) => Math.abs(other - at) < 13);
  const day = (iso: string) => new Date(iso).toLocaleDateString(undefined, { day: "numeric", month: "short" });
  return (
    <div className="score-history" ref={box}>
      <svg viewBox={`0 0 ${W} ${H}`} width={W} height={H} role="img" aria-label="score history">
        {ranks.map(([name, v]) => (
          <g key={name}>
            <line className="rank-line" x1={padL} x2={W - padR} y1={y(v)} y2={y(v)} />
            <text className="rank-label" x={4} y={y(v) + 3.5}>
              {name}
            </text>
          </g>
        ))}
        <path className="spark-line" d={steps.join(" ")} />
        {sorted.map((p, i) => {
          const isBest = bests.includes(i);
          return (
            <circle
              key={i}
              className={isBest ? "best" : "play"}
              cx={x(new Date(p.when).getTime(), i)}
              cy={y(p.achievement)}
              r={isBest ? 4.5 : 3}
            />
          );
        })}
        <text className="axis" x={padL} y={H - 6}>
          {day(sorted[0].when)}
        </text>
        {day(sorted[0].when) !== day(sorted[sorted.length - 1].when) && (
          <text className="axis end" x={W - padR} y={H - 6}>
            {day(sorted[sorted.length - 1].when)}
          </text>
        )}
        {room(y(hi) + 6) && (
          <text className="axis" x={4} y={y(hi) + 10}>
            {hi.toFixed(1)}
          </text>
        )}
        {room(y(lo) - 6) && (
          <text className="axis" x={4} y={y(lo) - 2}>
            {lo.toFixed(1)}
          </text>
        )}
      </svg>
    </div>
  );
}
