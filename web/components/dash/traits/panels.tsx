"use client";

import { getJSON, type Trait, type TraitFamily, type TraitPractice } from "../api";
import { Jacket, Label, TitleLink, type OpenChart } from "../bits";
import { useEffect, useState } from "react";
import { useTranslations } from "next-intl";
import { useLocale } from "@/components/I18n";
import { traitName } from "@/lib/i18n/traits";
import { activeTag } from "@/lib/i18n/active";
import { CONFIRM_CHARTS, LEAN, TIER, chance, isLean, isWatch, odds } from "./rules";

export function List({ items, tone, empty }: { items: Trait[]; tone: "down" | "up"; empty: string }) {
  const m = useTranslations("traitsTab");
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
            {t.read ? <span className="trait-read" title={m("measuredTitle")}>{m("notes")}</span> : null}
            {isLean(t) ? <span className="trait-lean">{m("leaning")}</span> : null}
            {isWatch(t) ? <span className="trait-lean">{m("watching")}</span> : null}
          </span>
          <span className="mono dim" title={`${m("countTitle", { charts: t.count, plays: t.plays ?? 0 })}${t.p ? ` · ${chance(t.p, m)}` : ""}`}>
            {odds(t.p) ? <small className="trait-odds">{m("oneIn", { n: odds(t.p) })}</small> : null}
            {t.count}
            {t.plays ? <small>{m("plays", { n: t.plays })}</small> : null}
          </span>
        </li>
      ))}
    </ul>
  );
}

export function Practice({ items, onOpen }: { items: TraitPractice[]; onOpen?: OpenChart }) {
  const m = useTranslations("traitsTab");
  const locale = useLocale();
  return (
    <ul className="practice">
      {items.map((p) => (
        <li key={p.label}>
          <div className="practice-head">
            <span className="mono trait-offset down">{p.offset.toFixed(2)}</span>
            <span>
              {traitName(p.label, p.english, locale)}
              {p.verified ? null : <span className="trait-lean">{m("leaning")}</span>}
            </span>
            <span className="mono">{m("charts", { n: p.count })}</span>
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
                    ? m("notPlayed")
                    : c.stale
                      ? m("oldScore", { n: c.accuracy.toFixed(2) })
                      : m("youHave", { n: c.accuracy.toFixed(4) })}
                </span>
              </li>
            ))}
          </ul>
        </li>
      ))}
    </ul>
  );
}

// the dimensions practice_for can name charts for; the rest are about the hands or the era, not any chart
const PRACTISABLE = new Set(["pattern", "slide", "touch", "density", "tempo", "hold"]);

/** Any measured pattern the player picks, with charts in their band to practise it on: the weak ones above are the model's
 *  choice, this is theirs. */
export function PracticePicker({ axes, listed, onOpen }: { axes: Trait[]; listed: TraitPractice[]; onOpen?: OpenChart }) {
  const m = useTranslations("traitsTab");
  const locale = useLocale();
  const [label, setLabel] = useState("");
  const [data, setData] = useState<Record<string, TraitPractice | null>>({});
  const [error, setError] = useState("");
  const shown = new Set(listed.map((p) => p.label));
  // measured on enough charts to mean something, as the lists above require
  const choices = axes.filter((a) => PRACTISABLE.has(a.dimension) && a.count >= CONFIRM_CHARTS && !shown.has(a.label)).sort((a, b) => a.offset - b.offset);
  useEffect(() => {
    if (!label || label in data) return;
    getJSON<{ practice: TraitPractice | null }>(`/api/me/practice?trait=${encodeURIComponent(label)}`)
      .then((d) => setData((prev) => ({ ...prev, [label]: d.practice })))
      .catch((e: Error) => setError(e.message));
  }, [label, data]);
  if (!choices.length) return null;
  const entry = label ? data[label] : undefined;
  return (
    <>
      <div className="ledger-head">
        <Label info={m("practiceAnyInfo")}>{m("practiceAny")}</Label>
      </div>
      <select className="practice-pick" value={label} onChange={(e) => { setError(""); setLabel(e.target.value); }} aria-label={m("practiceAny")}>
        <option value="">{m("practicePick")}</option>
        {choices.map((a) => (
          <option key={`${a.dimension}:${a.label}`} value={a.label}>
            {traitName(a.label, a.english, locale)} ({a.offset > 0 ? "+" : ""}{a.offset.toFixed(2)})
          </option>
        ))}
      </select>
      {error ? <p className="hint">{error}</p> : entry ? <Practice items={[entry]} onOpen={onOpen} /> : entry === null ? <p className="hint">{m("practiceNone")}</p> : null}
    </>
  );
}

/** The families, as a wheel and a list that opens. A family is drawn from the charts behind it, so a
 *  tag measured on nine of them cannot take the same room as one measured on ninety. */
export function Families({ families }: { families: TraitFamily[] }) {
  const m = useTranslations("traitsTab");
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
                {m("familyCount", { traits: f.traits, charts: f.charts.toLocaleString(activeTag()) })}
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
                    <span className="trait-when">{chance(t.p, m)}</span>
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
  const m = useTranslations("traitsTab");
  const sep = useTranslations("list")("sep");
  const locale = useLocale();
  const names = even.slice(0, 10).map((t) => traitName(t.label, t.english, locale));
  return (
    <p className="even-line">
      <b>{m("aboutEven")}</b> {names.join(sep)}
      {even.length > 10 ? m("andMore", { n: even.length - 10 }) : ""}
      {m("evenNote", { lean: LEAN.toFixed(1) })}
    </p>
  );
}
