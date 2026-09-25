"use client";

import type { Trait, TraitFamily, TraitPractice } from "../api";
import { Empty, Info, Jacket, Label, TitleLink, type OpenChart } from "../bits";
import { useState } from "react";
import { LEAN, TIER, chance, isLean, isWatch, odds } from "./rules";

export function List({ items, tone, empty }: { items: Trait[]; tone: "down" | "up"; empty: string }) {
  if (!items.length) return <p className="hint">{empty}</p>;
  return (
    <ul className="traits">
      {items.map((t) => (
        <li key={`${t.dimension}:${t.label}`}>
          <span className={`mono trait-offset ${tone}`}>
            {t.offset > 0 ? "+" : ""}
            {t.offset.toFixed(2)}
          </span>
          <span className="trait-label">
            {t.english ?? t.label}
            {t.read ? <span className="trait-read" title="measured from the chart's own notes, not written by an editor">notes</span> : null}
            {isLean(t) ? <span className="trait-lean">leaning</span> : null}
            {isWatch(t) ? <span className="trait-lean">worth watching</span> : null}
          </span>
          <span className="mono dim" title={`${t.count} charts${t.plays ? `, ${t.plays} plays` : ""}${t.p ? ` · ${chance(t.p)}` : ""}`}>
            {odds(t.p) ? <small className="trait-odds">1 in {odds(t.p)} · </small> : null}
            {t.count}
            {t.plays ? <small> · {t.plays} plays</small> : null}
          </span>
        </li>
      ))}
    </ul>
  );
}

export function Practice({ items, onOpen }: { items: TraitPractice[]; onOpen?: OpenChart }) {
  return (
    <ul className="practice">
      {items.map((p) => (
        <li key={p.label}>
          <div className="practice-head">
            <span className="mono trait-offset down">{p.offset.toFixed(2)}</span>
            <span>
              {p.english}
              {p.verified ? null : <span className="trait-lean">leaning</span>}
            </span>
            <span className="mono">{p.count} charts</span>
          </div>
          <ul>
            {p.charts.map((c) => (
              <li key={`${c.title}:${c.chart_type}:${c.difficulty}`}>
                <Jacket cover={c.cover} size={28} />
                <span>
                  <TitleLink title={c.title} type={c.chart_type} difficulty={c.difficulty} onOpen={onOpen} />{" "}
                  <span className="mono dim">
                    {TIER[c.difficulty] ?? c.difficulty} {c.level} · {c.constant.toFixed(1)} {c.chart_type.toUpperCase()}
                  </span>
                </span>
                <span className="mono">
                  {c.accuracy === null
                    ? "not played yet"
                    : c.stale
                      ? `an old ${c.accuracy.toFixed(2)}%`
                      : `you hold ${c.accuracy.toFixed(4)}%`}
                </span>
              </li>
            ))}
          </ul>
        </li>
      ))}
    </ul>
  );
}

/** The families, as a wheel and a list that opens. A family is drawn from the charts behind it, so a
 *  tag measured on nine of them cannot take the same room as one measured on ninety. */
export function Families({ families }: { families: TraitFamily[] }) {
  const [open, setOpen] = useState<string>("");
  return (
    <ul className="families">
      {families.map((f) => {
        const shown = open === f.key;
        return (
          <li key={f.key} className={shown ? "open" : ""}>
            <button type="button" onClick={() => setOpen(shown ? "" : f.key)} aria-expanded={shown}>
              <span className={`mono trait-offset ${f.offset < 0 ? "down" : "up"}`}>
                {f.offset > 0 ? "+" : ""}
                {f.offset.toFixed(2)}
              </span>
              <span className="trait-label">
                {f.label}
                {f.verified ? "" : " ?"}
                <span className="dim">{f.note}</span>
              </span>
              <span className="mono dim">
                {f.traits} traits · {f.charts.toLocaleString()} charts between them
              </span>
            </button>
            {shown && (
              <ul className="traits inside">
                {f.inside.map((t) => (
                  <li key={`${t.dimension}:${t.label}`}>
                    <span className={`mono trait-offset ${t.offset < 0 ? "down" : "up"}`}>
                      {t.offset > 0 ? "+" : ""}
                      {t.offset.toFixed(2)}
                    </span>
                    <span className="trait-label">{t.english ?? t.label}</span>
                    <span className="mono dim">{t.count}</span>
                    <span className="trait-when">{chance(t.p)}</span>
                  </li>
                ))}
              </ul>
            )}
          </li>
        );
      })}
    </ul>
  );
}


export function EvenLine({ even }: { even: Trait[] }) {
  const names = even.slice(0, 10).map((t) => t.english ?? t.label);
  return (
    <p className="even-line">
      <b>Level with the rest:</b> {names.join(", ")}
      {even.length > 10 ? ` and ${even.length - 10} more` : ""}. Measured over enough charts and within ±{LEAN.toFixed(1)} of your usual score: not a weakness, not a
      strength.
    </p>
  );
}
