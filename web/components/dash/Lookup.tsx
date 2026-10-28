import { useEffect, useRef, useState } from "react";
import dynamic from "next/dynamic";
import { useTranslations } from "next-intl";
import { ApiError, getJSON, type ChartDetail, type LookupTarget, type Overview, type SearchHit, type SongLookup } from "./api";
import { Chip, Empty, Jacket, chartHref, openInPlace, pct } from "./bits";
import { Detail } from "./Detail";
import { PatternBrowser } from "./PatternBrowser";

// Watch the chart is off until the AstroDX folders are back on the server: its code is kept, and uncommenting this and the <Watch> line below puts the button back
// // the player's code is only fetched once someone asks to watch a chart
// const Viewer = dynamic(() => import("@/components/play/Viewer").then((m) => m.Viewer), { ssr: false });
//
// /** The chart played in the page with its song, at the speeds saved in the player's settings (the game's 4.50 when none are). */
// function Watch({ song, chart, settings }: { song: SongLookup; chart: ChartDetail; settings?: Overview["settings"] }) {
//   const t = useTranslations("lookupTab");
//   const [held, setHeld] = useState<{ maidata: string; slot: number } | null>(null);
//   const [state, setState] = useState("");      // "loading", or why it failed
//   const params = new URLSearchParams({ title: song.title, type: chart.chart_type, difficulty: chart.difficulty });
//   const load = () => {
//     setState("loading");
//     getJSON<{ maidata: string; slot: number }>(`/api/me/viewer?${params}`)
//       .then((d) => { setHeld(d); setState(""); })
//       .catch((e: Error) => setState(t("watchFailed", { why: e.message })));
//   };
//   if (held) return <Viewer maidata={held.maidata} slot={held.slot} audio={`/api/me/track?${params}`} label={`${song.title} ${chart.difficulty}`}
//     noteSpeed={Number(settings?.note_speed) || 550} touchSpeed={Number(settings?.touch_speed) || 350} />;
//   return (
//     <div className="btn-row" style={{ marginTop: 18 }}>
//       <button type="button" className="button pink" onClick={load} disabled={state === "loading"}>{state === "loading" ? t("watchLoading") : t("watch")}</button>
//       {state && state !== "loading" && <span className="hint">{state}</span>}
//     </div>
//   );
// }

/** The Look up tab: find any song, then one chart the way /chart shows it. */
export function Lookup({ target, settings }: { target: LookupTarget | null; settings?: Overview["settings"] }) {
  const t = useTranslations("lookupTab");
  const list = useTranslations("list");
  const [query, setQuery] = useState(target?.title ?? "");
  const [hits, setHits] = useState<SearchHit[] | null>(null);
  const [song, setSong] = useState<SongLookup | null>(null);
  const [selected, setSelected] = useState(0);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [browseOpen, setBrowseOpen] = useState(false);
  const [browseTag, setBrowseTag] = useState("");
  const timer = useRef<number | null>(null);
  const opened = useRef<string>("");
  const opening = useRef(0);      // a lookup that a newer search or lookup has overtaken must not land on the page

  // a trait on a chart page opens the browser on that trait, so "what else asks this of me" is one click
  const browseTrait = (key: string) => {
    setSong(null);
    setHits(null);
    setError("");
    setBrowseTag(key);
    setBrowseOpen(true);
  };
  const searchNow = (wanted: string) =>
    getJSON<{ songs: SearchHit[] }>(`/api/me/search?q=${encodeURIComponent(wanted)}`);

  const open = (title: string, type?: string, difficulty?: string, cover?: string) => {
    const mine = ++opening.current;
    setBusy(true);
    setError("");
    const params = new URLSearchParams(cover ? { cover } : { title });
    if (type) params.set("type", type);
    if (difficulty) params.set("difficulty", difficulty);
    getJSON<SongLookup>(`/api/me/chart?${params}`)
      .then((d) => {
        if (mine !== opening.current) return;
        setSong(d);
        setSelected(d.selected);
        setHits(null);
        setQuery(d.title);
        const chart = d.charts[d.selected];
        window.history.replaceState(
          null,
          "",
          `${window.location.pathname}?chart=${encodeURIComponent(d.title)}&type=${chart?.chart_type ?? ""}&difficulty=${chart?.difficulty ?? ""}#chart`,
        );
      })
      .catch((e: ApiError) => {
        if (mine !== opening.current) return;
        setHits(null);
        if (e.status === 404 && e.code === "unknown_song") {
          const rows = (e.body.charts as { level: string; difficulty: string; accuracy: number }[] | undefined) ?? [];
          const yours = rows.map((c) => t("yourRow", { difficulty: c.difficulty, level: c.level, accuracy: c.accuracy.toFixed(4) })).join(list("sep"));
          setError(t("notInDb", { title: String(e.body.title ?? title), yours, one: String(rows.length === 1) }));
        } else setError(e.status === 404 ? t("noSong", { title }) : e.message);
      })
      .finally(() => {
        if (mine === opening.current) setBusy(false);
      });
  };

  // a title handed over from another tab, or from the address bar
  useEffect(() => {
    if (!target) return;
    const stamp = `${target.title}|${target.cover ?? ""}|${target.type ?? ""}|${target.difficulty ?? ""}`;
    if (opened.current === stamp && song) return;     // the same chart again while it is on show; once it is left, a repeat opens it
    opened.current = stamp;
    open(target.title, target.type, target.difficulty, target.cover);
  }, [target]); // eslint-disable-line react-hooks/exhaustive-deps

  const [searchError, setSearchError] = useState("");
  const search = (text: string) => {
    setQuery(text);
    opening.current++;      // a lookup still in flight belongs to the old query
    setSong(null);          // a new search is a new page: whatever chart was open goes with the old query
    setError("");
    setBusy(false);
    if (timer.current) window.clearTimeout(timer.current);
    const wanted = text.trim();
    if (wanted.length < 1) {
      setHits(null);
      return;
    }
    timer.current = window.setTimeout(() => {
      timer.current = null;
      searchNow(wanted)
        .then((d) => {
          setSearchError("");
          setHits(d.songs);
        })
        .catch((e: Error) => {
          setSearchError(e.message);
          setHits([]);
        });
    }, 220);
  };

  const chart = song?.charts[selected];
  return (
    <div className="lookup">
      <div className="search-row">
        <input
          className="search"
          type="text"
          role="searchbox"
          placeholder={t("placeholder")}
          value={query}
          onChange={(e) => search(e.target.value)}
          onKeyDown={(e) => {
            if (e.key !== "Enter" || !query.trim()) return;
            const wanted = query.trim();
            if (timer.current) {
              // typed and entered inside the debounce: the hits on hand belong to an earlier query
              window.clearTimeout(timer.current);
              timer.current = null;
              searchNow(wanted)
                .then((d) => open(d.songs[0]?.title ?? wanted))
                .catch(() => open(wanted));
              return;
            }
            open(hits?.[0]?.title ?? wanted);
          }}
          aria-label={t("label")}
          autoComplete="off"
        />
      </div>
      {hits !== null && (
        <ul className="hits">
          {hits.length === 0 && <li className="empty">{searchError ? t("searchFailed", { why: searchError }) : t("noMatches")}</li>}
          {hits.map((h) => (
            <li key={h.title} className="hit">
              <Jacket cover={h.cover} size={44} />
              <a className="hit-title" href={chartHref(h.title, "", "")} onClick={(e) => openInPlace(e, () => open(h.title))}>
                {h.title}
                {h.alias ? <span className="alias">{h.alias}</span> : null}
                <small>
                  {h.artist}
                  {h.charters?.length ? <span className="charter">{t("chartedBy", { who: h.charters.join(list("sep")) })}</span> : null}
                </small>
              </a>
              <div className="hit-charts">
                {h.charts.map((c) => (
                  <a
                    key={`${c.chart_type}|${c.difficulty}`}
                    href={chartHref(h.title, c.chart_type, c.difficulty)}
                    onClick={(e) => openInPlace(e, () => open(h.title, c.chart_type, c.difficulty))}
                    title={c.played ? `${pct(c.accuracy)} ${c.rank}` : t("neverPlayed")}
                  >
                    <span className={c.played ? "" : "faded"} style={{ display: "contents" }}>
                      <Chip difficulty={c.difficulty} level={c.level} type={c.chart_type} />
                    </span>
                  </a>
                ))}
              </div>
            </li>
          ))}
        </ul>
      )}
      {busy && <Empty>{t("looking")}</Empty>}
      {error && <Empty>{error}</Empty>}
      {!busy && !song && hits === null && !error && (
        <Empty>{t("intro")}</Empty>
      )}
      {!song && hits === null && (
        <PatternBrowser
          onOpen={(title, type, difficulty) => {
            open(title, type, difficulty);
          }}
          open={browseOpen}
          setOpen={setBrowseOpen}
          tag={browseTag}
          setTag={setBrowseTag}
        />
      )}
      {song && chart && !busy && <Detail song={song} chart={chart} selected={selected} onSelect={setSelected} onTrait={browseTrait} />}
      {/* {song && chart && !busy && chart.viewer && <Watch key={`${song.title}|${chart.chart_type}|${chart.difficulty}`} song={song} chart={chart} settings={settings} />} */}
    </div>
  );
}
