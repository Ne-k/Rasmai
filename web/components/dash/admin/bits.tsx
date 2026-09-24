"use client";

import { Fragment } from "react";
import { num } from "../bits";
import type { AdminData, Person, Table } from "./types";

export const SLICES = ["#ff3d8f", "#5cd3e8", "#f0c04a", "#8f7dff", "#4fd18b", "#ff9f5c", "#9aa0b5"];

export function size(bytes: number | null | undefined): string {
  if (bytes === null || bytes === undefined) return "—";
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1048576) return `${(bytes / 1024).toFixed(0)} KB`;
  return `${(bytes / 1048576).toFixed(2)} MB`;
}

export function duration(seconds: number | undefined): string {
  if (seconds === undefined || Number.isNaN(seconds)) return "—";
  const d = Math.floor(seconds / 86400);
  const h = Math.floor((seconds % 86400) / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  return d ? `${d}d ${h}h` : h ? `${h}h ${m}m` : `${m}m`;
}

export function Facts({ rows }: { rows: [string, React.ReactNode][] }) {
  return (
    <dl className="facts">
      {rows.map(([key, value]) => (
        <Fragment key={key}>
          <dt>{key}</dt>
          <dd className="mono">{value}</dd>
        </Fragment>
      ))}
    </dl>
  );
}

/** A limit and how much of it is in use, as a filled track. */
export function Gauge({ label, used, total }: { label: string; used: number; total: number }) {
  const share = total > 0 ? Math.min(100, (100 * used) / total) : 0;
  return (
    <div className="gauge">
      <span className="gauge-top">
        <span>{label}</span>
        <span className="mono">
          {num(used)} <span className="dim">/ {num(total)}</span>
        </span>
      </span>
      <span className="bar">
        <span style={{ width: `${Math.max(share, used > 0 ? 4 : 0)}%` }} />
      </span>
    </div>
  );
}

/** Plays per day over the last month, with the days nobody played left empty. */
export function Activity({ days }: { days: AdminData["activity"] }) {
  const peak = Math.max(1, ...days.map((d) => d.plays));
  const total = days.reduce((sum, d) => sum + d.plays, 0);
  return (
    <>
      <div className="admin-bars" role="img" aria-label={`${total} plays recorded over the last 30 days`}>
        {days.map((d) => (
          <span key={d.day} className={`admin-bar${d.plays ? "" : " empty"}`} title={`${d.day}: ${d.plays} plays, ${d.people} accounts`}>
            <span style={{ height: `${d.plays ? Math.max(3, (100 * d.plays) / peak) : 2}%` }} />
          </span>
        ))}
      </div>
      <div className="admin-axis mono">
        <span>{days[0]?.day.slice(5)}</span>
        <span className="dim">peak {num(peak)} in a day</span>
        <span>{days[days.length - 1]?.day.slice(5)}</span>
      </div>
    </>
  );
}

/** What fills the database, as one stacked bar plus its key. */
export function Composition({ tables, total }: { tables: Table[]; total: number }) {
  const sized = tables.filter((t) => t.bytes !== null) as { name: string; bytes: number }[];
  if (!sized.length) return null;
  const top = sized.slice(0, 6);
  const rest = sized.slice(6).reduce((sum, t) => sum + t.bytes, 0);
  const parts = rest > 0 ? [...top, { name: "everything else", bytes: rest }] : top;
  return (
    <>
      <div className="stack" role="img" aria-label="what fills the database">
        {parts.map((t, i) => (
          <span
            key={t.name}
            title={`${t.name}: ${size(t.bytes)}`}
            style={{ width: `${(100 * t.bytes) / Math.max(1, total)}%`, background: SLICES[i % SLICES.length] }}
          />
        ))}
      </div>
      <ul className="keys">
        {parts.map((t, i) => (
          <li key={t.name}>
            <i style={{ background: SLICES[i % SLICES.length] }} />
            <span className="mono">{t.name}</span>
            <b className="mono">{size(t.bytes)}</b>
          </li>
        ))}
      </ul>
    </>
  );
}

export function Who({ person, id }: { person: Person; id: string }) {
  return (
    <span className="who">
      {person.avatar ? <img src={person.avatar} alt="" width={26} height={26} loading="lazy" /> : <span className="who-blank" />}
      <span className="who-text">
        <b>{person.name || id}</b>
        <span className="mono dim">{person.handle ? `@${person.handle}` : id}</span>
      </span>
    </span>
  );
}
