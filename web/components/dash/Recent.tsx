"use client";

import { Fragment, useState } from "react";
import { getJSON, type PlayDetail, type RecentPlay } from "./api";
import { Chip, Empty, Jacket, Label, Lamp, TitleLink, num, pct, type OpenChart } from "./bits";

const PAGE = 60;
const NOTE_ORDER = ["tap", "hold", "slide", "touch", "break"];
const JUDGES = ["critical", "perfect", "great", "good", "miss"] as const;

type Opened = PlayDetail | "loading" | { error: string };

function Judgements({ detail }: { detail: PlayDetail }) {
  const kinds = NOTE_ORDER.filter((k) => detail.notes[k]);
  const total = (j: (typeof JUDGES)[number]) => kinds.reduce((sum, k) => sum + detail.notes[k][j], 0);
  const lostAll = Object.values(detail.lost).reduce((a, b) => a + b, 0);
  const cost = (v: number | undefined) => (v && v >= 0.005 ? `-${v.toFixed(2)}%` : "");
  return (
    <>
      <table className="tbl compact judge">
        <thead>
          <tr>
            <th>notes</th>
            {JUDGES.map((j) => (
              <th key={j} className="c-num">
                {j}
              </th>
            ))}
            <th className="c-num">lost</th>
          </tr>
        </thead>
        <tbody>
          {kinds.map((k) => (
            <tr key={k}>
              <td className="mono">{k}</td>
              {JUDGES.map((j) => (
                <td key={j} className={`c-num mono${j === "miss" && detail.notes[k][j] ? " lost" : ""}`}>
                  {detail.notes[k][j]}
                </td>
              ))}
              <td className={`c-num mono${(detail.lost[k] ?? 0) >= 0.5 ? " lost" : ""}`}>{cost(detail.lost[k])}</td>
            </tr>
          ))}
          <tr className="total">
            <td className="mono">all</td>
            {JUDGES.map((j) => (
              <td key={j} className="c-num mono">
                {total(j)}
              </td>
            ))}
            <td className="c-num mono">{cost(lostAll)}</td>
          </tr>
        </tbody>
      </table>
      <p className="hint">
        fast {detail.fast} · late {detail.late} · combo {num(detail.combo)} / {num(detail.max_combo)}
        {detail.max_sync ? ` · sync ${num(detail.sync)} / ${num(detail.max_sync)}` : ""}
        {lostAll >= 0.005 ? ` · ${(101 - lostAll).toFixed(4)}% after what each note type cost` : ""}
      </p>
    </>
  );
}

export function Recent({ plays, total, onOpen }: { plays: RecentPlay[] | null; total: number; onOpen?: OpenChart }) {
  const [shown, setShown] = useState(PAGE);
  const [open, setOpen] = useState<Record<string, Opened>>({});
  const toggle = (idx: string) => {
    if (open[idx]) {
      setOpen(({ [idx]: _gone, ...rest }) => rest);
      return;
    }
    setOpen((o) => ({ ...o, [idx]: "loading" }));
    getJSON<PlayDetail>(`/api/me/play?idx=${encodeURIComponent(idx)}`)
      .then((d) => setOpen((o) => ({ ...o, [idx]: d })))
      .catch((e: Error) => setOpen((o) => ({ ...o, [idx]: { error: e.message || "could not read the play" } })));
  };
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
                <Fragment key={`${p.day}T${p.time}|${p.position}`}>
                <tr className={p.pb ? "pb" : ""}>
                  <td className="c-time" data-l="time">{p.time}</td>
                  <td className="c-jacket">
                    <Jacket cover={p.cover} size={32} />
                  </td>
                  <td className="c-title">
                    <TitleLink title={p.title} type={p.chart_type} difficulty={p.difficulty} onOpen={onOpen} />
                    <Chip difficulty={p.difficulty} level={p.level} constant={p.constant} type={p.chart_type} />
                    {p.pb && <span className="tag-b50">new best</span>}
                    {p.idx && (
                      <button type="button" className="judge-btn" aria-expanded={Boolean(open[p.idx])} onClick={() => toggle(p.idx!)}>
                        {open[p.idx] ? "hide judgements" : "judgements"}
                      </button>
                    )}
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
                {p.idx && open[p.idx] && (
                  <tr className="judge-row">
                    <td colSpan={7}>
                      {open[p.idx] === "loading" ? (
                        <p className="hint">reading the play from maimai DX NET…</p>
                      ) : "error" in (open[p.idx] as object) ? (
                        <p className="hint">{(open[p.idx] as { error: string }).error}</p>
                      ) : (
                        <Judgements detail={open[p.idx] as PlayDetail} />
                      )}
                    </td>
                  </tr>
                )}
                </Fragment>
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
