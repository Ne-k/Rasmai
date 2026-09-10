import { useEffect, useRef, useState } from "react";
import type { HistoryPoint } from "./api";
import { day } from "./bits";

type Props = { points: HistoryPoint[]; field?: "rating" | "best50" };

/** Rating over time. The drawing is sized to the box it sits in, so the labels stay readable on a phone. */
export function Sparkline({ points, field = "rating" }: Props) {
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

  const sorted = [...points].sort((a, b) => a.recordedAt.localeCompare(b.recordedAt));
  const values = sorted.map((p) => p[field]);
  if (sorted.length < 2) {
    return (
      <div className="spark one" ref={box}>
        <span className="label">rating over time</span>
        <p>
          {sorted.length ? `One point so far: ${values[0]}.` : "No history yet."} Each analysis adds a point, so this fills in as you play.
        </p>
      </div>
    );
  }
  const W = width;
  const H = width < 480 ? 130 : 150;
  const padX = 8;
  const padTop = 14;
  const padBottom = 22;
  const min = Math.min(...values);
  const max = Math.max(...values);
  const span = Math.max(max - min, 10);
  const lo = min - span * 0.15;
  const hi = max + span * 0.15;
  const x = (i: number) => padX + (i * (W - padX * 2)) / (sorted.length - 1);
  const y = (v: number) => padTop + ((hi - v) / (hi - lo)) * (H - padTop - padBottom);
  const path = values.map((v, i) => `${i ? "L" : "M"}${x(i).toFixed(1)} ${y(v).toFixed(1)}`).join(" ");
  const last = sorted.length - 1;
  const gain = values[last] - values[0];
  return (
    <div className="spark" ref={box}>
      <div className="spark-head">
        <span className="label">rating over time</span>
        <span className={`delta ${gain >= 0 ? "up" : "down"}`}>
          {gain >= 0 ? "+" : ""}
          {gain} since {day(sorted[0].recordedAt)}
        </span>
      </div>
      <svg viewBox={`0 0 ${W} ${H}`} width={W} height={H} role="img" aria-label={`${field} history`}>
        <line className="grid" x1={padX} x2={W - padX} y1={y(max)} y2={y(max)} />
        <line className="grid" x1={padX} x2={W - padX} y1={y(min)} y2={y(min)} />
        <path className="line" d={path} />
        {values.map((v, i) => (
          <circle key={i} className={i === last ? "dot last" : "dot"} cx={x(i)} cy={y(v)} r={i === last ? 5 : 3} />
        ))}
        <text className="axis" x={padX} y={y(max) - 5}>
          {max}
        </text>
        <text className="axis" x={padX} y={y(min) + 13}>
          {min}
        </text>
        <text className="axis" x={padX} y={H - 4}>
          {day(sorted[0].recordedAt)}
        </text>
        <text className="axis end" x={W - padX} y={H - 4}>
          {day(sorted[last].recordedAt)}
        </text>
      </svg>
    </div>
  );
}
