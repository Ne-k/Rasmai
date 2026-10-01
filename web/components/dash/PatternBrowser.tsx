import { useEffect, useRef, useState } from "react";
import { useLocale, useM } from "@/components/I18n";
import { traitName } from "@/lib/i18n/traits";
import { ApiError, getJSON, type PatternBrowse } from "./api";
import { Chip, Empty, Jacket, pct } from "./bits";

const LEVELS = ["", "15", "14+", "14", "13+", "13", "12+", "12", "11+", "11", "10+", "10", "9+", "9", "8+", "8", "7+", "7"];

const DIFFS: [string, string][] = [["", ""], ["remaster", "Re:MASTER"], ["master", "MASTER"], ["expert", "EXPERT"], ["advanced", "ADVANCED"], ["basic", "BASIC"]];

/** Browse charts by what they ask of you: a trait, narrowed by level or difficulty, with your own scores beside each. */
export function PatternBrowser({ onOpen, open, setOpen, tag, setTag }: {
  onOpen: (title: string, type: string, difficulty: string) => void;
  open: boolean;
  setOpen: (v: boolean) => void;
  tag: string;
  setTag: (v: string) => void;
}) {
  const m = useM();
  const t = m.patterns;
  const locale = useLocale();
  const [find, setFind] = useState("");
  const [level, setLevel] = useState("");
  const [diff, setDiff] = useState("");
  const [data, setData] = useState<PatternBrowse | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const request = useRef(0);      // only the latest request may answer: two quick clicks must not settle on the older list
  useEffect(() => {
    if (!open) return;
    const mine = ++request.current;
    setBusy(true);
    setError("");
    const params = new URLSearchParams({ tag, level, difficulty: diff });
    getJSON<PatternBrowse>(`/api/me/patterns?${params}`)
      .then((d) => {
        if (mine === request.current) setData(d);
      })
      .catch((e: ApiError) => {
        if (mine === request.current) setError(e.message);
      })
      .finally(() => {
        if (mine === request.current) setBusy(false);
      });
  }, [open, tag, level, diff]);
  if (!open) {
    return (
      <button type="button" className="linkish browse-toggle" onClick={() => setOpen(true)}>
        {t.open}
      </button>
    );
  }
  const tags = data?.tags ?? [];
  const needle = find.trim().toLowerCase();
  const matches = needle
    ? tags.filter((x) => x.tag.toLowerCase().includes(needle) || x.english.toLowerCase().includes(needle) || x.label.toLowerCase().includes(needle) || traitName(x.label, x.english, locale).toLowerCase().includes(needle))
    : tags;
  const chosen = tags.find((x) => x.tag === data?.tag);     // the trait the list on show belongs to, not the one just clicked
  return (
    <section className="browse">
      <div className="filters">
        <input
          className="search"
          type="text"
          role="searchbox"
          value={find}
          placeholder={t.placeholder}
          aria-label={t.label}
          onChange={(e) => setFind(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && matches.length) setTag(matches[0].tag);
          }}
        />
        <select value={level} onChange={(e) => setLevel(e.target.value)} aria-label={m.newTab.level}>
          {LEVELS.map((l) => (
            <option key={l || "any"} value={l}>
              {l ? m.picksTab.level(l) : m.picksTab.anyLevel}
            </option>
          ))}
        </select>
        <select value={diff} onChange={(e) => setDiff(e.target.value)} aria-label={m.newTab.difficulty}>
          {DIFFS.map(([v, label]) => (
            <option key={v || "any"} value={v}>
              {label || t.anyDifficulty}
            </option>
          ))}
        </select>
        <button type="button" className="linkish" onClick={() => setOpen(false)}>
          {t.close}
        </button>
      </div>
      {error && <Empty>{error}</Empty>}
      {!error && (
        <ul className="tag-picker">
          {matches.length === 0 && <li className="hint">{t.noMatch(find)}</li>}
          {matches.map((x) => (
            <li key={x.tag}>
              <button
                type="button"
                className={[x.tag === tag ? "on" : "", x.community ? "" : "measured"].filter(Boolean).join(" ")}
                onClick={() => setTag(x.tag === tag ? "" : x.tag)}
                title={x.community ? t.taggedTitle(x.charts) : t.measuredTitle(x.charts)}
              >
                {x.community ? (locale === "ja" ? x.tag : `${x.english} · ${x.tag}`) : traitName(x.label, x.english, locale)}
                <span className="mono"> {x.charts}</span>
              </button>
            </li>
          ))}
        </ul>
      )}
      {!error && !tag && (
        <p className="hint">{t.intro}</p>
      )}
      {tag && data && data.tag && (
        <>
          <p className="hint">
            <b>{chosen && !chosen.community ? traitName(chosen.label, chosen.english, locale) : locale === "ja" ? data.tag : data.english}</b>
            {chosen && !chosen.community ? t.measured : locale === "ja" ? "" : ` · ${data.tag}`}{t.charts(data.charts.length)}
            {data.charts.some((c) => c.played) ? t.played(data.charts.filter((c) => c.played).length) : ""}
            {busy ? t.updating : ""}
          </p>
          {data.charts.length === 0 ? (
            <Empty>{t.none}</Empty>
          ) : (
            <ul className="hits pattern-list">
              {data.charts.map((c) => (
                <li key={`${c.title}|${c.chart_type}|${c.difficulty}`} className="hit">
                  <Jacket cover={c.cover} size={44} />
                  <button type="button" className="hit-title" onClick={() => onOpen(c.title, c.chart_type, c.difficulty)}>
                    {c.title}
                    <small>
                      {c.played ? `${pct(c.accuracy)} ${c.rank} · ${c.rating}${c.note ? ` · ${c.note}` : ""}` : t.neverPlayed}
                      {c.tags.length ? t.also(c.tags.map((x) => traitName(x, undefined, locale)).join(m.list.sep)) : ""}
                    </small>
                  </button>
                  <div className="hit-charts">
                    <span className={c.played ? "" : "faded"} style={{ display: "contents" }}>
                      <Chip difficulty={c.difficulty} level={c.level} constant={c.constant} type={c.chart_type} />
                    </span>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </>
      )}
    </section>
  );
}
