"use client";

import type { Trait, TraitFamily, TraitPractice } from "../api";
import { Empty, Info, Jacket, Label, TitleLink, type OpenChart } from "../bits";
import { useState } from "react";
import { useLocale, useM } from "@/components/I18n";
import { traitName } from "@/lib/i18n/traits";
import { activeTag } from "@/lib/i18n/active";
import { LEAN, TIER, chance, isLean, isWatch, odds } from "./rules";

export function List({ items, tone, empty }: { items: Trait[]; tone: "down" | "up"; empty: string }) {
  const m = useM().traitsTab;
  const locale = useLocale();
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
            {traitName(t.label, t.english, locale)}
            {t.read ? <span className="trait-read" title={m.measuredTitle}>{m.notes}</span> : null}
            {isLean(t) ? <span className="trait-lean">{m.leaning}</span> : null}
            {isWatch(t) ? <span className="trait-lean">{m.watching}</span> : null}
          </span>
          <span className="mono dim" title={`${m.countTitle(t.count, t.plays ?? 0)}${t.p ? ` · ${chance(t.p)}` : ""}`}>
            {odds(t.p) ? <small className="trait-odds">{m.oneIn(odds(t.p))}</small> : null}
            {t.count}
            {t.plays ? <small>{m.plays(t.plays)}</small> : null}
          </span>
        </li>
      ))}
    </ul>
  );
}

export function Practice({ items, onOpen }: { items: TraitPractice[]; onOpen?: OpenChart }) {
  const m = useM().traitsTab;
  const locale = useLocale();
  return (
    <ul className="practice">
      {items.map((p) => (
        <li key={p.label}>
          <div className="practice-head">
            <span className="mono trait-offset down">{p.offset.toFixed(2)}</span>
            <span>
              {traitName(p.label, p.english, locale)}
              {p.verified ? null : <span className="trait-lean">{m.leaning}</span>}
            </span>
            <span className="mono">{m.charts(p.count)}</span>
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
                    ? m.notPlayed
                    : c.stale
                      ? m.oldScore(c.accuracy.toFixed(2))
                      : m.youHave(c.accuracy.toFixed(4))}
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
  const m = useM().traitsTab;
  const locale = useLocale();
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
                {traitName(f.label, undefined, locale)}
                {f.verified ? "" : " ?"}
                <span className="dim">{f.note}</span>
              </span>
              <span className="mono dim">
                {m.familyCount(f.traits, f.charts.toLocaleString(activeTag()))}
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
                    <span className="trait-label">{traitName(t.label, t.english, locale)}</span>
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
  const all = useM();
  const m = all.traitsTab;
  const locale = useLocale();
  const names = even.slice(0, 10).map((t) => traitName(t.label, t.english, locale));
  return (
    <p className="even-line">
      <b>{m.aboutEven}</b> {names.join(all.list.sep)}
      {even.length > 10 ? m.andMore(even.length - 10) : ""}
      {m.evenNote(LEAN.toFixed(1))}
    </p>
  );
}
