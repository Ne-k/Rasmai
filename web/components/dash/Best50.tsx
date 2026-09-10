"use client";

import { type ChartRow, type Overview } from "./api";
import { Chip, Empty, Jacket, Label, TitleLink, num, pct, type OpenChart } from "./bits";

export function levelValue(level: string): number {
  const n = parseFloat(level.replace("+", ""));
  return level.endsWith("+") ? n + 0.5 : n;
}

type Cutoffs = NonNullable<Overview["analysis"]>["best50"];

export function Best50({ charts, cutoffs, onOpen }: { charts: ChartRow[] | null; cutoffs?: Cutoffs; onOpen?: OpenChart }) {
  if (!charts) return <Empty>Loading…</Empty>;
  const inPool = charts.filter((c) => c.inBest50).sort((a, b) => b.rating - a.rating);
  const fresh = inPool.filter((c) => c.new);
  const older = inPool.filter((c) => !c.new);
  const pool = (title: string, rows: ChartRow[], size: number, total?: number, cutoff?: number) => (
    <section className="ledger">
      <div className="ledger-head">
        <Label info={size === 15 ? "The 15 best chart ratings on songs from the current version. Enters at is the chart rating a score needs to get in." : "The 35 best chart ratings on songs from earlier versions. Enters at is the chart rating a score needs to get in."}>
          {title} · {rows.length}/{size}
        </Label>
        <span className="mono hint">
          {total != null ? `${num(total)} total` : ""}
          {cutoff ? ` · enters at ${cutoff}` : ""}
        </span>
      </div>
      <table className="tbl compact b50 keep">
        <thead>
          <tr>
            <th className="c-n">#</th>
            <th className="c-jacket" aria-label="jacket" />
            <th>chart</th>
            <th className="c-num">const</th>
            <th className="c-num">achievement</th>
            <th className="c-num">rating</th>
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
              <td className="c-num mono dim c-const">{r.constant.toFixed(1)}</td>
              <td className="c-num mono c-acc">
                {pct(r.accuracy)} <b>{r.rank}</b>
              </td>
              <td className="c-num mono strong c-rating">{r.rating}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
  return (
    <div className="two-up wide-right">
      {pool("new version", fresh, 15, cutoffs?.newTotal, cutoffs?.newCutoff)}
      {pool("older versions", older, 35, cutoffs?.oldTotal, cutoffs?.oldCutoff)}
    </div>
  );
}
