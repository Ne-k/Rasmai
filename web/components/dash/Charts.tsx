import { useMemo, useRef, useState } from "react";
import { useM } from "@/components/I18n";
import { getJSON, type ChartRow } from "./api";
import { Chip, Empty, Jacket, Label, Lamp, num, pct } from "./bits";
import { TitleLink, type OpenChart } from "./bits";

const DIFFS = ["all", "remaster", "master", "expert", "advanced", "basic"];
const RANKS = ["all", "SSS+", "SSS", "SS+", "SS", "S+", "S", "AAA", "AA", "A", "below A"];
type SortKey = "rating" | "constant" | "accuracy" | "title" | "plays" | "dx" | "bestMatch";
// the words for each are in the translation files, under the same key and direction
const SORTS: { key: SortKey; desc: boolean }[] = [
  { key: "rating", desc: true },
  { key: "bestMatch", desc: true },
  { key: "constant", desc: true },
  { key: "constant", desc: false },
  { key: "accuracy", desc: false },
  { key: "accuracy", desc: true },
  { key: "dx", desc: true },
  { key: "plays", desc: true },
  { key: "title", desc: false },
];

export function Charts({ rows, onOpen }: { rows: ChartRow[]; onOpen?: OpenChart }) {
  const m = useM();
  const t = m.chartsTab;
  const c = m.cols;
  const [query, setQuery] = useState("");
  const [diff, setDiff] = useState("all");
  const [type, setType] = useState("all");
  const [rank, setRank] = useState("all");
  const [pool, setPool] = useState("all");
  const [sort, setSort] = useState<SortKey>("rating");
  const [desc, setDesc] = useState(true);
  const [shown, setShown] = useState(100);
  const [titles, setTitles] = useState<string[] | null>(null);
  const timerId = useRef<number | null>(null);

  function executeTitleSearch(query: string): void {
    query = query.trim();
    if (!query) {
      setTitles(null);
      return;
    }
    getJSON<{ titles: string[] }>(`/api/me/titles?q=${encodeURIComponent(query)}`)
      .then((found) => setTitles(found.titles))
      .catch(console.error);
  }

  function searchTitles(query: string) {
    query = query.trim();
    if (timerId.current) window.clearTimeout(timerId.current);
    if (!query) {
      setTitles(null);
      return;
    }
    timerId.current = window.setTimeout(() => {
      timerId.current = null;
      executeTitleSearch(query);
    }, 220);
  }

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    // "13.8" is a constant, "13" or "13+" a level; anything else is looked for in the title and artist
    const constant = /^\d{1,2}\.\d$/.test(q) ? Number(q) : null;
    const level = /^\d{1,2}\+?$/.test(q) ? q : null;
    const out = rows.filter((r) => {
      if (diff !== "all" && r.difficulty !== diff) return false;
      if (type !== "all" && r.type !== type) return false;
      if (pool === "new" && !r.new) return false;
      if (pool === "old" && r.new) return false;
      if (pool === "b50" && !r.inBest50) return false;
      if (rank !== "all") {
        if (rank === "below A") {
          if (["SSS+", "SSS", "SS+", "SS", "S+", "S", "AAA", "AA", "A"].includes(r.rank)) return false;
        } else if (r.rank !== rank) return false;
      }
      if (constant !== null) return Math.abs(r.constant - constant) < 0.05;
      if (level !== null) return r.level === level;
      // "13." half-typed lands here too and is searched as a title. A chart the title search missed
      // (it stops at 100 hits) still shows when its title or artist contains the query
      if (titles && !titles.includes(r.title)) {
        if (q && !r.title.toLowerCase().includes(q) && !r.artist.toLowerCase().includes(q)) return false;
      }
      return true;
    });
    const dir = desc ? -1 : 1;
    out.sort((a, b) => {
      if (sort === "title") return dir * a.title.localeCompare(b.title, "ja");
      if (sort === "bestMatch") {
        if (titles) {
          const aLocation = titles.indexOf(a.title);
          const bLocation = titles.indexOf(b.title);
          // a chart the search didn't return goes after every one it did
          if (aLocation === bLocation) return b.rating - a.rating;
          if (aLocation === -1) return 1;
          if (bLocation === -1) return -1;
          return aLocation - bLocation;
        } else return b.rating - a.rating;
      }
      const av = a[sort] as number;
      const bv = b[sort] as number;
      if (av === bv) return b.rating - a.rating;
      return dir * (av - bv);
    });
    return out;
  }, [rows, query, diff, type, rank, pool, sort, desc, titles]);

  const header = (key: SortKey, label: string, cls = "", span = 1) => (
    <th className={`${cls} sortable ${sort === key ? "on" : ""}`} colSpan={span} aria-sort={sort === key ? (desc ? "descending" : "ascending") : "none"}>
      <button
        type="button"
        className="sort-btn"
        onClick={() => {
          if (sort === key) setDesc(!desc);
          else {
            setSort(key);
            setDesc(key !== "title");
          }
        }}
      >
        {label}
        {sort === key ? <span className="arrow" aria-hidden="true">{desc ? "▾" : "▴"}</span> : null}
      </button>
    </th>
  );

  const totalRating = filtered.reduce((s, r) => s + r.rating, 0);
  return (
    <>
      <div className="filters">
        <input
          className="search"
          type="text"
          role="searchbox"
          placeholder={t.search}
          value={query}
          onChange={(e) => {
            setQuery(e.target.value);
            searchTitles(e.target.value);
          }}
          onKeyDown={(e) => {
            // Enter searches now rather than opening the top row: sorted by rating, that row can be a poor title match
            const wanted = query.trim();
            if (e.key !== "Enter" || wanted.length < 1) return;
            if (timerId.current) {
              // typed and entered inside the debounce: the hits on hand belong to an earlier query
              window.clearTimeout(timerId.current);
              timerId.current = null;
              return;
            }
            executeTitleSearch(wanted);
          }}
        />
        <select value={diff} onChange={(e) => setDiff(e.target.value)} aria-label={m.newTab.difficulty}>
          {DIFFS.map((d) => (
            <option key={d} value={d}>
              {d === "all" ? t.allDiffs : d === "remaster" ? "Re:MASTER" : d.toUpperCase()}
            </option>
          ))}
        </select>
        <select value={type} onChange={(e) => setType(e.target.value)} aria-label={t.type}>
          <option value="all">{t.bothTypes}</option>
          <option value="dx">{t.dxOnly}</option>
          <option value="std">{t.stdOnly}</option>
        </select>
        <select value={rank} onChange={(e) => setRank(e.target.value)} aria-label={c.rank}>
          {RANKS.map((r) => (
            <option key={r} value={r}>
              {r === "all" ? t.anyRank : r === "below A" ? t.belowA : r}
            </option>
          ))}
        </select>
        <select value={pool} onChange={(e) => setPool(e.target.value)} aria-label={t.pool}>
          <option value="all">{t.allCharts}</option>
          <option value="b50">{t.inBest50}</option>
          <option value="new">{t.current}</option>
          <option value="old">{t.older}</option>
        </select>
        <select
          value={`${sort}|${desc ? "d" : "a"}`}
          onChange={(e) => {
            const [key, dir] = e.target.value.split("|");
            setSort(key as SortKey);
            setDesc(dir === "d");
          }}
          aria-label={t.sort}
        >
          {SORTS.map((s) => (
            <option key={`${s.key}|${s.desc ? "d" : "a"}`} value={`${s.key}|${s.desc ? "d" : "a"}`}>
              {t.sorts[`${s.key}|${s.desc ? "d" : "a"}`]}
            </option>
          ))}
        </select>
      </div>
      <div className="ledger-head">
        <Label info={t.countInfo}>
          {t.count(num(filtered.length), num(rows.length))}
        </Label>
        <span className="mono hint">{t.totalRating(num(totalRating))}</span>
      </div>
      {filtered.length === 0 ? (
        <Empty>{t.noMatch}</Empty>
      ) : (
        <div className="scroll">
        <table className="tbl">
          <thead>
            <tr>
              {header("title", c.chart, "c-title-h", 2)}
              {header("constant", c.constant, "c-num")}
              {header("accuracy", c.achievement, "c-num")}
              <th>{c.rank}</th>
              <th>{c.lamp}</th>
              {header("dx", c.dx, "c-num")}
              {header("plays", c.plays, "c-num")}
              {header("rating", c.rating, "c-num")}
            </tr>
          </thead>
          <tbody>
            {filtered.slice(0, shown).map((r) => (
              <tr key={`${r.title}|${r.type}|${r.difficulty}`} className={r.inBest50 ? "in-b50" : ""}>
                <td className="c-jacket">
                  <Jacket cover={r.cover} size={32} />
                </td>
                <td className="c-title">
                  <TitleLink title={r.title} type={r.type} difficulty={r.difficulty} onOpen={onOpen} />
                  <Chip difficulty={r.difficulty} level={r.level} constant={r.constant} type={r.type} />
                  {r.inBest50 && <span className="tag-b50">{t.best50}</span>}
                  {r.estimated && (
                    <span className="tag-est" title={t.estimatedTitle}>
                      {t.estimated}
                    </span>
                  )}
                </td>
                <td className="c-num mono" data-l={c.constant}>{r.constant.toFixed(1)}</td>
                <td className="c-num mono strong" data-l={c.achievement}>{pct(r.accuracy, 4)}</td>
                <td className="mono" data-l={c.rank}>{r.rank}</td>
                <td data-l={c.lamp}>
                  <Lamp fc={r.fc} fs={r.fs} />
                </td>
                <td className="c-num mono dim" data-l={c.dx}>
                  {r.dx > 0 ? num(r.dx) : "—"}
                  {r.maxDx > 0 && r.dx > 0 ? <small> / {num(r.maxDx)}</small> : null}
                </td>
                <td className="c-num mono dim" data-l={c.plays}>{r.plays > 0 ? r.plays : "—"}</td>
                <td className="c-num mono strong" data-l={c.rating}>{r.rating}</td>
              </tr>
            ))}
          </tbody>
        </table>
        </div>
      )}
      {filtered.length > shown && (
        <div className="more">
          <button type="button" className="button ghost" onClick={() => setShown(shown + 200)}>
            {t.more(Math.min(200, filtered.length - shown))}
          </button>
        </div>
      )}
    </>
  );
}
