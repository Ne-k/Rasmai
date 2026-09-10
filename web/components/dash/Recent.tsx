"use client";

import { useState } from "react";
import { type RecentPlay } from "./api";
import { Chip, Empty, Jacket, Label, Lamp, TitleLink, num, pct, type OpenChart } from "./bits";

const PAGE = 60;

export function Recent({ plays, total, onOpen }: { plays: RecentPlay[] | null; total: number; onOpen?: OpenChart }) {
  const [shown, setShown] = useState(PAGE);
  if (!plays) return <Empty>Loading…</Empty>;
  if (!plays.length)
    return (
      <Empty>
        No plays stored yet. Every read, a command in Discord or the read-now button on the Account tab, keeps the plays on the recent-plays
        page, and they stay here for as long as the account is linked. Turn on the daily read with <code>/settings history</code> so none fall
        off maimai&apos;s fifty-play list between reads.
      </Empty>
    );
  const visible = plays.slice(0, shown);
  const days: [string, RecentPlay[]][] = [];
  for (const p of visible) {
    if (days.length && days[days.length - 1][0] === p.day) days[days.length - 1][1].push(p);
    else days.push([p.day, [p]]);
  }
  const oldest = plays[plays.length - 1];
  return (
    <>
      <p className="hint">
        {num(total)} plays stored since {oldest ? new Date(oldest.day).toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" }) : "linking"}
        {total > plays.length ? `, the latest ${num(plays.length)} shown` : ""}. Every read adds the plays it sees, and they stay for as long
        as the account is linked.
      </p>
      {days.map(([d, group]) => (
        <section className="ledger" key={d}>
          <div className="ledger-head">
            <Label>{new Date(d).toLocaleDateString(undefined, { weekday: "short", day: "numeric", month: "short", year: "numeric" })}</Label>
            <span className="mono hint">
              {group.length} plays · {group.filter((p) => p.pb).length} new bests
            </span>
          </div>
          <table className="tbl compact">
            <thead>
              <tr>
                <th>time</th>
                <th aria-label="jacket" />
                <th>chart</th>
                <th className="c-num">achievement</th>
                <th>lamp</th>
                <th className="c-num">dx score</th>
                <th className="c-num">rating</th>
              </tr>
            </thead>
            <tbody>
              {group.map((p) => (
                <tr key={`${p.day}T${p.time}|${p.position}`} className={p.pb ? "pb" : ""}>
                  <td className="c-time" data-l="time">{p.time}</td>
                  <td className="c-jacket">
                    <Jacket cover={p.cover} size={32} />
                  </td>
                  <td className="c-title">
                    <TitleLink title={p.title} type={p.chart_type} difficulty={p.difficulty} onOpen={onOpen} />
                    <Chip difficulty={p.difficulty} level={p.level} constant={p.constant} type={p.chart_type} />
                    {p.pb && <span className="tag-b50">new best</span>}
                  </td>
                  <td className="c-num mono strong" data-l="achievement">
                    {pct(p.achievement, 4)} <b>{p.rank}</b>
                  </td>
                  <td data-l="lamp">
                    <Lamp fc={p.fc} fs={p.fs} />
                  </td>
                  <td className="c-num mono dim" data-l="dx score">{p.dx ? (p.max_dx ? `${num(p.dx)} / ${num(p.max_dx)}` : num(p.dx)) : "—"}</td>
                  <td className="c-num mono" data-l="rating">{p.chart_rating || "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      ))}
      {plays.length > shown && (
        <div className="more">
          <button type="button" className="button ghost" onClick={() => setShown(shown + PAGE)}>
            show {Math.min(PAGE, plays.length - shown)} more
          </button>
        </div>
      )}
    </>
  );
}
