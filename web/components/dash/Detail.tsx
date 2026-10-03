import { useEffect, useState } from "react";
import { useTranslations } from "next-intl";
import { useLocale } from "@/components/I18n";
import { activeTag } from "@/lib/i18n/active";
import { noteKind, traitName } from "@/lib/i18n/traits";
import { getJSON, type ChartDetail, type SongLookup, type UnlockArea } from "./api";
import { Chip, Empty, Jacket, Label, Lamp, num, pct } from "./bits";
import { Observed } from "./Cohort";
import { ScoreHistory } from "./ScoreHistory";

/** A constant revised since the first recorded play: the history was scored against the old number until then. */
function constNote(chart: { history: { when: string; constant: number }[]; constant: number }, t: ReturnType<typeof useTranslations<"detail">>): string {
  const first = chart.history.reduce((a, b) => (a.when < b.when ? a : b));
  return Math.abs(first.constant - chart.constant) >= 0.05 ? t("constNote", { n: first.constant.toFixed(1) }) : "";
}

const NOTE_KINDS = ["tap", "hold", "slide", "touch", "break"] as const;

/** The five DX stars in Rasmai's star mark, the unearned ones faded. */
function DxStars({ n }: { n: number }) {
  const t = useTranslations("detail");
  return (
    <span className="dxstars" role="img" aria-label={t("stars", { n })}>
      {[0, 1, 2, 3, 4].map((i) => (
        <img key={i} src="/marks/dxstar.svg" alt="" width={14} height={14} className={i < n ? undefined : "off"} />
      ))}
    </span>
  );
}

/** A chart's day of arrival, read as a plain date rather than a moment, so no timezone moves it. */
function arrived(iso: string): string {
  const [y, m, d] = iso.slice(0, 10).split("-").map(Number);
  if (!y || !m || !d) return "";
  return new Date(y, m - 1, d).toLocaleDateString(activeTag(), { day: "numeric", month: "short", year: "numeric" });
}

/** What the chart is made of, as one band: the share of each note type, with the counts beneath it. */
function NoteMix({ split }: { split: Record<string, number> | null }) {
  const locale = useLocale();
  const sep = useTranslations("list")("sep");
  if (!split) return null;
  const parts = NOTE_KINDS.map((kind) => [kind, split[kind] ?? 0] as const).filter(([, n]) => n > 0);
  const total = parts.reduce((sum, [, n]) => sum + n, 0);
  if (!total) return null;
  const share = (n: number) => (100 * n) / total;
  return (
    <div className="note-mix">
      <div className="note-bar" role="img" aria-label={parts.map(([kind, n]) => `${n} ${noteKind(kind, locale)}`).join(sep)}>
        {parts.map(([kind, n]) => (
          <span key={kind} className={`nm-${kind}`} style={{ width: `${share(n)}%` }} title={`${num(n)} ${noteKind(kind, locale)} · ${Math.round(share(n))}%`} />
        ))}
      </div>
      <p className="note-legend mono">
        {parts.map(([kind, n]) => (
          <span key={kind}>
            <i className={`nm-${kind}`} aria-hidden="true" />
            {num(n)} {noteKind(kind, locale)}
          </span>
        ))}
      </p>
    </div>
  );
}

/** Which cabinets have this chart. The search spans every region, so the page says where each song
 *  can actually be played rather than leaving a player to find out at the machine. */
function Where({ regions, intl }: { regions?: string[]; intl?: boolean }) {
  const t = useTranslations("detail");
  const where = regions?.length ? regions : intl === false ? ["jp", "cn"] : ["jp", "intl", "cn"];
  const everywhere = where.length >= 3;
  return (
    <span className={`chart-flag${everywhere ? " chart-flag-quiet" : ""}`} title={t("regionsTitle")}>
      {everywhere ? t("everywhere") : where.map((r) => (t.has(`regions.${r}` as never) ? t(`regions.${r}` as never) : r)).join(" · ")}
      {where.length === 1 ? t("only") : ""}
    </span>
  );
}

export const RANK_LINES: [string, number][] = [["S", 97], ["S+", 98], ["SS", 99], ["SS+", 99.5], ["SSS", 100], ["SSS+", 100.5]];

export function Detail({ song, chart, selected, onSelect, onTrait }: { song: SongLookup; chart: ChartDetail; selected: number; onSelect: (i: number) => void; onTrait?: (key: string) => void }) {
  const t = useTranslations("detail");
  const c = useTranslations("cols");
  const locale = useLocale();
  const tier = (key: string) => (t.has(`tier.${key}` as never) ? t(`tier.${key}` as never) : key);
  // the chart videos and unlock notes come from the wiki and can take a few seconds the first time; the page does not wait for them
  const [wiki, setWiki] = useState<{ videos: Record<string, string>; unlock: string[]; unlockAreas: UnlockArea[]; wiki: string } | null>(null);
  useEffect(() => {
    let live = true;
    setWiki(null);
    getJSON<{ videos: Record<string, string>; unlock: string[]; unlockAreas?: UnlockArea[]; wiki: string }>(`/api/me/video?title=${encodeURIComponent(song.title)}`)
      .then((d) => live && setWiki({ videos: d.videos ?? {}, unlock: d.unlock ?? [], unlockAreas: d.unlockAreas ?? [], wiki: d.wiki ?? "" }))
      .catch(() => live && setWiki({ videos: {}, unlock: [], unlockAreas: [], wiki: "" }));
    return () => {
      live = false;
    };
  }, [song.title]);
  const video = wiki?.videos[`${chart.chart_type}|${chart.difficulty}`] ?? chart.video;
  const facts = [song.alias, song.reading, song.genre, song.bpm ? t("bpm", { n: song.bpm }) : "", song.version, chart.is_new ? t("currentVersion") : ""].filter(Boolean);
  const p = chart.prediction;
  const bothTypes = new Set(song.charts.map((c) => c.chart_type)).size > 1;
  return (
    <section className="detail">
      <div className="detail-head">
        <Jacket cover={song.cover} size={96} />
        <h2>{song.title}</h2>
        <p className="artist">{song.artist || t("artistUnknown")}</p>
        <span className="facts label">{facts.join(" · ")}</span>
      </div>

      <div className="chart-pick" role="group" aria-label={t("charts")}>
        {song.charts.map((c, i) => (
          <button key={`${c.chart_type}|${c.difficulty}`} type="button" aria-pressed={i === selected} className={i === selected ? "on" : ""} onClick={() => onSelect(i)}>
            <span className={c.played ? "" : "faded"} style={{ display: "contents" }}>
              <Chip difficulty={c.difficulty} level={c.level} constant={c.constant} type={bothTypes ? c.chart_type : undefined} />
            </span>
          </button>
        ))}
      </div>
      <p className="hint chart-meta">
        {tier(chart.difficulty)} {chart.level}{t("constant", { n: chart.constant.toFixed(1) })}
        {chart.notes ? t("notes", { n: num(chart.notes) }) : ""}
        {chart.designer ? t("chartedBy", { who: chart.designer }) : ""}
        {chart.released ? t("added", { when: arrived(chart.released) }) : ""}
        <Where regions={chart.regions} intl={chart.intl} />
        {chart.deleted && <span className="chart-flag">{t("removed")}</span>}
      </p>
      {chart.observed && <Observed {...chart.observed} />}
      <NoteMix split={chart.noteSplit} />
      {chart.patterns.length > 0 && (
        <>
          <ul className="patterns">
            {chart.patterns.map((p) => (
              <li key={p.key} className={[p.community ? "" : "measured", p.offset != null ? (p.offset < 0 ? "down" : "up") : ""].filter(Boolean).join(" ")}>
                <button
                  type="button"
                  onClick={() => onTrait?.(p.key)}
                  title={`${p.community ? t("tagged") : t("measured")}${t("clickTrait")}`}
                >
                  {traitName(p.label, undefined, locale)}
                  {p.offset != null ? <span className="mono"> {p.offset > 0 ? "+" : ""}{p.offset.toFixed(1)}</span> : null}
                </button>
              </li>
            ))}
          </ul>
          <p className="hint pattern-note">
            {t("clickOne")}
            {chart.patterns.some((p) => p.community) ? t("communityNote") : t("measuredNote")}
            {chart.patterns.some((p) => p.offset != null) ? t("offsetNote") : ""}
          </p>
        </>
      )}

      <div className="fact-grid">
        {chart.played ? (
          <>
            <div className="fact wide">
              <div className="k">{t("yourScore")}</div>
              <div className="v">
                {pct(chart.accuracy, 4)} <small>{chart.rank}</small>
                <em>{t("rating", { n: chart.rating ?? 0 })}</em>
              </div>
            </div>
            <div className="fact">
              <div className="k">{t("lamp")}</div>
              <div className="v">
                <Lamp fc={chart.fc ?? ""} fs={chart.fs ?? ""} />
              </div>
            </div>
            <div className="fact">
              <div className="k">{t("dx")}</div>
              <div className="v">{chart.dx ? num(chart.dx) : "—"}</div>
              <div className="s">{chart.max_dx ? <>{t("of", { n: num(chart.max_dx) })}<DxStars n={chart.stars ?? 0} /></> : t("maxUnknown")}</div>
            </div>
            <div className="fact">
              <div className="k">{t("plays")}</div>
              <div className="v">{chart.plays ? num(chart.plays) : "—"}</div>
              <div className="s">{chart.plays ? t("fromNet") : t("playsUnknown")}</div>
            </div>
            <div className="fact">
              <div className="k">{t("best50")}</div>
              <div className="v" style={{ fontSize: 15 }}>{chart.note || "—"}</div>
            </div>
          </>
        ) : (
          <div className="fact wide">
            <div className="k">{t("yourScore")}</div>
            <div className="v">
              {t("neverPlayed")}
              {chart.usual != null && <em>{t("usual", { n: chart.usual.toFixed(1) })}</em>}
            </div>
            <div className="s">{chart.note || ""}</div>
          </div>
        )}
        {p && (
          <div className="fact wide pink">
            <div className="k">{t("prediction")}</div>
            <div className="v">
              {pct(p.expected)} <small>{p.rank}</small>
              <em>
                {t("range", { low: p.low.toFixed(1), high: p.high.toFixed(1) })}
              </em>
            </div>
            <div className="s">
              {chart.played && p.new_best != null
                ? t("newBest", { n: Math.round(p.new_best * 100) })
                : t("firstTry")}
              {Math.abs(p.tier_offset) >= 0.5 ? t("tierOffset", { tier: tier(p.tier), n: `${p.tier_offset >= 0 ? "+" : ""}${p.tier_offset.toFixed(1)}` }) : ""}
            </div>
          </div>
        )}
      </div>

      {chart.ladder.length > 0 && (
        <section className="ledger">
          <div className="ledger-head">
            <Label info={t("ladderInfo")}>{chart.played ? t("ladderPlayed") : t("ladderNew")}</Label>
            <span className="mono hint">{chart.played ? t("ladderHintPlayed") : t("ladderHintNew")}</span>
          </div>
          <table className="tbl compact ladder keep">
            <thead>
              <tr>
                <th>{c("rank")}</th>
                <th className="c-num">{t("need")}</th>
                <th className="c-num">{c("rating")}</th>
                <th className="c-num">{c("gain")}</th>
                <th>{c("odds")}</th>
              </tr>
            </thead>
            <tbody>
              {chart.ladder.map((step) => (
                <tr key={step.rank} className={step.odds >= 0.25 && step.gain > 0 ? "reach" : ""}>
                  <td className="mono strong">{step.rank}</td>
                  <td className="c-num mono">{step.need.toFixed(2)}%</td>
                  <td className="c-num mono">{step.rating}</td>
                  <td className={`c-num mono ${step.gain > 0 ? "gain" : "dim"}`}>{step.gain > 0 ? `+${step.gain}` : "—"}</td>
                  <td className="odds mono">
                    <span className="odds-bar">
                      <span style={{ width: `${Math.max(2, Math.round(step.odds * 100))}%` }} />
                    </span>
                    {Math.round(step.odds * 100)}%
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      )}

      <section className="ledger">
        <div className="ledger-head">
          <Label info={t("unlockInfo")}>{t("unlock")}</Label>
          <span className="mono hint">{wiki?.wiki ? <a href={wiki.wiki} target="_blank" rel="noopener noreferrer">SilentBlue RemyWiki</a> : t("fromWiki")}</span>
        </div>
        {wiki === null ? (
          <Empty>{t("loadingWiki")}</Empty>
        ) : wiki.unlock.length ? (
          <ul className="unlock">
            {wiki.unlock.map((line, i) => (
              <li key={i}>
                {line}
                {wiki.unlockAreas
                  .filter((a) => a.line === i)
                  .map((a) => (
                    <a key={a.name} className="unlock-area" href={`/me/?area=${encodeURIComponent(a.name)}#areas`}>
                      {t("areaProgress", { title: a.title, where: a.state === "not_started" ? t("notStarted") : `${num(a.distance)} km` })}
                      {a.state === "completed" ? t("completed") : a.milestone ? t("nextAt", { km: num(a.milestone) }) : ""} →
                    </a>
                  ))}
              </li>
            ))}
          </ul>
        ) : (
          <Empty>{wiki.wiki ? t("noUnlock") : t("noPage")}</Empty>
        )}
      </section>

      <section className="ledger">
        <div className="ledger-head">
          <Label info={t("historyInfo")}>{t("history")}</Label>
          <span className="mono hint">{chart.history.length ? `${t("points", { n: chart.history.length })}${constNote(chart, t)}` : ""}</span>
        </div>
        <ScoreHistory points={chart.history} />
      </section>

      <div className="btn-row" style={{ marginTop: 18 }}>
        <a className="button ghost" href={video ?? chart.youtube} target="_blank" rel="noopener noreferrer">
          {video ? t("watch") : t("searchYoutube")}
        </a>
      </div>
    </section>
  );
}
