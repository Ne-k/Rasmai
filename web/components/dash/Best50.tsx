"use client";

import { useM } from "@/components/I18n";
import { type ChartRow, type Overview } from "./api";
import { Chip, Empty, Jacket, Label, TitleLink, num, pct, type OpenChart } from "./bits";

export function levelValue(level: string): number {
  const n = parseFloat(level.replace("+", ""));
  return level.endsWith("+") ? n + 0.5 : n;
}

type Cutoffs = NonNullable<Overview["analysis"]>["best50"];

export function Best50({ charts, cutoffs, onOpen }: { charts: ChartRow[] | null; cutoffs?: Cutoffs; onOpen?: OpenChart }) {
  const m = useM();
  const t = m.best50Tab;
  if (!charts) return <Empty>{m.dash.loading}</Empty>;
  const inPool = charts.filter((c) => c.inBest50).sort((a, b) => b.rating - a.rating);
  const fresh = inPool.filter((c) => c.new);
  const older = inPool.filter((c) => !c.new);
  const pool = (title: string, rows: ChartRow[], size: number, total?: number, cutoff?: number) => (
    <section className="ledger">
      <div className="ledger-head">
        <Label info={size === 15 ? t.newInfo : t.oldInfo}>
          {title} · {rows.length}/{size}
        </Label>
        <span className="mono hint">
          {total != null ? t.total(num(total)) : ""}
          {cutoff ? t.entersAt(cutoff) : ""}
        </span>
      </div>
      <table className="tbl compact b50 keep">
        <thead>
          <tr>
            <th className="c-n">#</th>
            <th className="c-jacket" aria-label={t.jacket} />
            <th>{t.chart}</th>
            <th className="c-num">{t.achievement}</th>
            <th className="c-num">{t.constRating}</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r, i) => (
            <tr key={`${r.title}|${r.type}|${r.difficulty}`}>
              <td className="c-n">{i + 1}</td>
              <td className="c-jacket">
                <Jacket cover={r.cover} size={32} />
              </td>
              <td className="c-title">
                <TitleLink title={r.title} type={r.type} difficulty={r.difficulty} onOpen={onOpen} />
                <Chip difficulty={r.difficulty} level={r.level} constant={r.constant} type={r.type} />
              </td>
              <td className="c-num mono c-acc">
                {pct(r.accuracy)} <b>{r.rank}</b>
                {r.dx > 0 && <span className="b50-sub dim">DX {num(r.dx)}{r.maxDx > 0 ? ` / ${num(r.maxDx)}` : ""}</span>}
              </td>
              <td className="c-num mono strong c-rating">
                {r.constant > 0 && <span className="b50-const dim">{r.constant.toFixed(1)} →</span>}
                {r.rating}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
  const mean = (pick: (c: ChartRow) => number) => inPool.reduce((sum, c) => sum + pick(c), 0) / inPool.length;
  return (
    <>
      {inPool.length > 0 && (
        <div className="readout b50-avg" aria-label={t.averages(inPool.length)}>
          <span className="lbl">{t.avgConstant}</span>
          <span className="val">{mean((c) => c.constant).toFixed(2)}</span>
          <span className="lbl">{t.avgAchievement}</span>
          <span className="val">{pct(mean((c) => c.accuracy))}</span>
          <span className="lbl">{t.avgRating}</span>
          <span className="val">{mean((c) => c.rating).toFixed(1)}</span>
        </div>
      )}
      <div className="two-up wide-right">
        {pool(t.newVersion, fresh, 15, cutoffs?.newTotal, cutoffs?.newCutoff)}
        {pool(t.older, older, 35, cutoffs?.oldTotal, cutoffs?.oldCutoff)}
      </div>
    </>
  );
}
