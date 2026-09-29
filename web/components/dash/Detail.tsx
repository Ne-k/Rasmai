import { useEffect, useState } from "react";
import { getJSON, type ChartDetail, type SongLookup, type UnlockArea } from "./api";
import { Chip, Empty, Jacket, Label, Lamp, num, pct } from "./bits";
import { ScoreHistory } from "./ScoreHistory";

/** A constant revised since the first recorded play: the history was scored against the old number until then. */
function constNote(chart: { history: { when: string; constant: number }[]; constant: number }): string {
  const first = chart.history.reduce((a, b) => (a.when < b.when ? a : b));
  return Math.abs(first.constant - chart.constant) >= 0.05 ? ` · const ${first.constant.toFixed(1)} when first recorded` : "";
}

const NOTE_KINDS = ["tap", "hold", "slide", "touch", "break"] as const;

/** The five DX stars in Rasmai's star mark, the unearned ones faded. */
function DxStars({ n }: { n: number }) {
  return (
    <span className="dxstars" role="img" aria-label={`${n} of 5 DX stars`}>
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
  return new Date(y, m - 1, d).toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" });
}

/** What the chart is made of, as one band: the share of each note type, with the counts beneath it. */
function NoteMix({ split }: { split: Record<string, number> | null }) {
  if (!split) return null;
  const parts = NOTE_KINDS.map((kind) => [kind, split[kind] ?? 0] as const).filter(([, n]) => n > 0);
  const total = parts.reduce((sum, [, n]) => sum + n, 0);
  if (!total) return null;
  const share = (n: number) => (100 * n) / total;
  return (
    <div className="note-mix">
      <div className="note-bar" role="img" aria-label={parts.map(([kind, n]) => `${n} ${kind}`).join(", ")}>
        {parts.map(([kind, n]) => (
          <span key={kind} className={`nm-${kind}`} style={{ width: `${share(n)}%` }} title={`${num(n)} ${kind} · ${Math.round(share(n))}%`} />
        ))}
      </div>
      <p className="note-legend mono">
        {parts.map(([kind, n]) => (
          <span key={kind}>
            <i className={`nm-${kind}`} aria-hidden="true" />
            {num(n)} {kind}
          </span>
        ))}
      </p>
    </div>
  );
}

const REGION_NAMES: Record<string, string> = { jp: "Japan", intl: "International", cn: "China" };

/** Which cabinets have this chart. The search spans every region, so the page says where each song
 *  can actually be played rather than leaving a player to find out at the machine. */
function Where({ regions, intl }: { regions?: string[]; intl?: boolean }) {
  const where = regions?.length ? regions : intl === false ? ["jp", "cn"] : ["jp", "intl", "cn"];
  const everywhere = where.length >= 3;
  return (
    <span className={`chart-flag${everywhere ? " chart-flag-quiet" : ""}`} title="regions that have this chart">
      {everywhere ? "every region" : where.map((r) => REGION_NAMES[r] ?? r).join(" · ")}
      {where.length === 1 ? " only" : ""}
    </span>
  );
}

const TIER: Record<string, string> = { basic: "Basic", advanced: "Advanced", expert: "Expert", master: "Master", remaster: "Re:Master" };

export const RANK_LINES: [string, number][] = [["S", 97], ["S+", 98], ["SS", 99], ["SS+", 99.5], ["SSS", 100], ["SSS+", 100.5]];

export function Detail({ song, chart, selected, onSelect, onTrait }: { song: SongLookup; chart: ChartDetail; selected: number; onSelect: (i: number) => void; onTrait?: (key: string) => void }) {
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
  const facts = [song.alias, song.reading, song.genre, song.bpm ? `BPM ${song.bpm}` : "", song.version, chart.is_new ? "current version" : ""].filter(Boolean);
  const p = chart.prediction;
  const bothTypes = new Set(song.charts.map((c) => c.chart_type)).size > 1;
  return (
    <section className="detail">
      <div className="detail-head">
        <Jacket cover={song.cover} size={96} />
        <h2>{song.title}</h2>
        <p className="artist">{song.artist || "artist unknown"}</p>
        <span className="facts label">{facts.join(" · ")}</span>
      </div>

      <div className="chart-pick" role="group" aria-label="Charts of this song">
        {song.charts.map((c, i) => (
          <button key={`${c.chart_type}|${c.difficulty}`} type="button" aria-pressed={i === selected} className={i === selected ? "on" : ""} onClick={() => onSelect(i)}>
            <span className={c.played ? "" : "faded"} style={{ display: "contents" }}>
              <Chip difficulty={c.difficulty} level={c.level} constant={c.constant} type={bothTypes ? c.chart_type : undefined} />
            </span>
          </button>
        ))}
      </div>
      <p className="hint chart-meta">
        {TIER[chart.difficulty] ?? chart.difficulty} {chart.level} · constant {chart.constant.toFixed(1)}
        {chart.notes ? ` · ${num(chart.notes)} notes` : ""}
        {chart.designer ? ` · charted by ${chart.designer}` : ""}
        {chart.released ? ` · added ${arrived(chart.released)}` : ""}
        <Where regions={chart.regions} intl={chart.intl} />
        {chart.deleted && <span className="chart-flag">removed from the game</span>}
      </p>
      <NoteMix split={chart.noteSplit} />
      {chart.patterns.length > 0 && (
        <>
          <ul className="patterns">
            {chart.patterns.map((p) => (
              <li key={p.key} className={[p.community ? "" : "measured", p.offset != null ? (p.offset < 0 ? "down" : "up") : ""].filter(Boolean).join(" ")}>
                <button
                  type="button"
                  onClick={() => onTrait?.(p.key)}
                  title={`${p.community ? "tagged by maiノーツ editors" : "measured from the chart's notes"} · click to see every chart with this`}
                >
                  {p.label}
                  {p.offset != null ? <span className="mono"> {p.offset > 0 ? "+" : ""}{p.offset.toFixed(1)}</span> : null}
                </button>
              </li>
            ))}
          </ul>
          <p className="hint pattern-note">
            Click one to see every chart with it.{" "}
            {chart.patterns.some((p) => p.community)
              ? "Solid tags come from maiノーツ editors. Dashed ones are measured from the chart's notes, BPM and density."
              : "These are measured from the chart's notes, BPM and density. maiノーツ editors haven't tagged this one. They mostly tag Master charts."}
            {chart.patterns.some((p) => p.offset != null) ? " The number is how your scores on it compare to your curve." : ""}
          </p>
        </>
      )}

      <div className="fact-grid">
        {chart.played ? (
          <>
            <div className="fact wide">
              <div className="k">your score</div>
              <div className="v">
                {pct(chart.accuracy, 4)} <small>{chart.rank}</small>
                <em>rating {chart.rating}</em>
              </div>
            </div>
            <div className="fact">
              <div className="k">lamp</div>
              <div className="v">
                <Lamp fc={chart.fc ?? ""} fs={chart.fs ?? ""} />
              </div>
            </div>
            <div className="fact">
              <div className="k">DX score</div>
              <div className="v">{chart.dx ? num(chart.dx) : "—"}</div>
              <div className="s">{chart.max_dx ? <>of {num(chart.max_dx)} · <DxStars n={chart.stars ?? 0} /></> : "max unknown"}</div>
            </div>
            <div className="fact">
              <div className="k">plays</div>
              <div className="v">{chart.plays ? num(chart.plays) : "—"}</div>
              <div className="s">{chart.plays ? "from maimai DX NET" : "unknown until the next refresh"}</div>
            </div>
            <div className="fact">
              <div className="k">best-50</div>
              <div className="v" style={{ fontSize: 15 }}>{chart.note || "—"}</div>
            </div>
          </>
        ) : (
          <div className="fact wide">
            <div className="k">your score</div>
            <div className="v">
              never played
              {chart.usual != null && <em>you&apos;d usually get ~{chart.usual.toFixed(1)}% here</em>}
            </div>
            <div className="s">{chart.note || ""}</div>
          </div>
        )}
        {p && (
          <div className="fact wide pink">
            <div className="k">prediction</div>
            <div className="v">
              {pct(p.expected)} <small>{p.rank}</small>
              <em>
                {p.low.toFixed(1)} to {p.high.toFixed(1)} on a good run
              </em>
            </div>
            <div className="s">
              {chart.played && p.new_best != null
                ? `${Math.round(p.new_best * 100)}% chance the next run is a new best`
                : "first try, based on how you play this level"}
              {Math.abs(p.tier_offset) >= 0.5 ? ` · your ${p.tier} scores are ${p.tier_offset >= 0 ? "+" : ""}${p.tier_offset.toFixed(1)} vs your curve` : ""}
            </div>
          </div>
        )}
      </div>

      {chart.ladder.length > 0 && (
        <section className="ledger">
          <div className="ledger-head">
            <Label info="What each rank needs, the rating it gives, what it adds to your best 50 and your odds of getting it. Highlighted rows are realistic.">{chart.played ? "what each rank is worth" : "what each rank would be worth"}</Label>
            <span className="mono hint">{chart.played ? "gain is what it adds to your best 50 · odds are how often you score that here" : "odds are for a first try"}</span>
          </div>
          <table className="tbl compact ladder keep">
            <thead>
              <tr>
                <th>Rank</th>
                <th className="c-num">Need</th>
                <th className="c-num">Rating</th>
                <th className="c-num">Gain</th>
                <th>Odds</th>
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
          <Label info="Unlock condition from SilentBlue RemyWiki. If it's an area, your distance there is shown too.">how to unlock</Label>
          <span className="mono hint">{wiki?.wiki ? <a href={wiki.wiki} target="_blank" rel="noopener noreferrer">SilentBlue RemyWiki</a> : "from SilentBlue RemyWiki"}</span>
        </div>
        {wiki === null ? (
          <Empty>Loading from the wiki…</Empty>
        ) : wiki.unlock.length ? (
          <ul className="unlock">
            {wiki.unlock.map((line, i) => (
              <li key={i}>
                {line}
                {wiki.unlockAreas
                  .filter((a) => a.line === i)
                  .map((a) => (
                    <a key={a.name} className="unlock-area" href={`/me/?area=${encodeURIComponent(a.name)}#areas`}>
                      your {a.title} progress: {a.state === "not_started" ? "not started" : `${a.distance.toLocaleString("en-US")} km`}
                      {a.state === "completed" ? ", completed" : a.milestone ? `, next reward at ${a.milestone.toLocaleString("en-US")} km` : ""} →
                    </a>
                  ))}
              </li>
            ))}
          </ul>
        ) : (
          <Empty>{wiki.wiki ? "No unlock condition on the wiki, so it should be unlocked by default." : "The wiki has no page for this song yet."}</Empty>
        )}
      </section>

      <section className="ledger">
        <div className="ledger-head">
          <Label info="Every play of this chart the bot has saved. Dots are plays and the line is your best.">score history</Label>
          <span className="mono hint">{chart.history.length ? `${chart.history.length} points${constNote(chart)}` : ""}</span>
        </div>
        <ScoreHistory points={chart.history} />
      </section>

      <div className="btn-row" style={{ marginTop: 18 }}>
        <a className="button ghost" href={video ?? chart.youtube} target="_blank" rel="noopener noreferrer">
          {video ? "watch the chart on YouTube" : "search YouTube for the chart"}
        </a>
      </div>
    </section>
  );
}
