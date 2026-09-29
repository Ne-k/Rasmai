import { useEffect, useState } from "react";
import { getJSON, type Picks as PicksData } from "./api";
import { Chip, Empty, Jacket, Label, LoadError, num, pct } from "./bits";
import { TitleLink, type OpenChart } from "./bits";

const LEVELS: { key: string; label: string; note: string }[] = [
  { key: "easy", label: "Easier", note: "safest targets, about 50/50 odds" },
  { key: "balanced", label: "Balanced", note: "best gain for the effort, about 1 in 4" },
  { key: "hard", label: "Challenging", note: "harder targets, about 1 in 6" },
  { key: "extreme", label: "Long shots", note: "biggest gains, about 1 in 10" },
];

const CHART_LEVELS = ["15", "14+", "14", "13+", "13", "12+", "12", "11+", "11", "10+", "10", "9+", "9", "8+", "8", "7+", "7"];
/** A level (13+), one constant (13.2) or a range (13.0-13.4); the server reads the same forms. */
const SCOPE_OK = /^(\d{1,2}\+?|\d{1,2}\.\d|\d{1,2}(\.\d)?\s*-\s*\d{1,2}(\.\d)?)$/;

export function Picks({ initial, onOpen }: { initial: string; onOpen?: OpenChart }) {
  const [challenge, setChallenge] = useState(LEVELS.some((l) => l.key === initial) ? initial : "balanced");
  const [chartLevel, setChartLevel] = useState("");
  const [constant, setConstant] = useState("");
  const [data, setData] = useState<Record<string, PicksData>>({});
  const [error, setError] = useState("");
  const typed = constant.trim();
  const scope = typed || chartLevel;
  const scopeOk = !scope || SCOPE_OK.test(scope);
  const key = `${challenge}|${scopeOk ? scope : ""}`;
  const picks = scopeOk ? data[key] : undefined;     // a half-typed constant shows the hint, not the unfiltered list

  useEffect(() => {
    if (data[key] || error || !scopeOk) return;
    const query = new URLSearchParams({ challenge });
    if (scope) query.set("level", scope);
    getJSON<PicksData>(`/api/me/picks?${query}`)
      .then((d) => setData((prev) => ({ ...prev, [key]: d })))
      .catch((e: Error) => setError(e.message));
  }, [key, challenge, scope, scopeOk, data, error]);

  const level = LEVELS.find((l) => l.key === challenge)!;
  return (
    <>
      <div className="row-between">
        <div className="seg" role="group" aria-label="How hard the targets are">
          {LEVELS.map((l) => (
            <button key={l.key} type="button" className={l.key === challenge ? "on" : ""} aria-pressed={l.key === challenge} onClick={() => setChallenge(l.key)}>
              {l.label}
            </button>
          ))}
        </div>
        <span className="hint">
          {level.note}
          {picks?.scope ? ` · picks and new charts filtered to ${picks.scope}. The road isn't filtered.` : ""}
        </span>
      </div>
      <div className="filters scope-filters">
        <select value={chartLevel} onChange={(e) => setChartLevel(e.target.value)} aria-label="Only this level" disabled={Boolean(typed)}>
          <option value="">any level</option>
          {CHART_LEVELS.map((l) => (
            <option key={l} value={l}>
              level {l}
            </option>
          ))}
        </select>
        <input
          className="search scope-constant"
          type="text"
          role="searchbox"
          value={constant}
          placeholder="or a constant like 13.2 or 13.0-13.4"
          aria-label="Only this constant or range"
          onChange={(e) => setConstant(e.target.value)}
        />
        {!scopeOk && <span className="hint">Use a level like 13+, a constant like 13.2, or a range like 13.0-13.4.</span>}
      </div>
      {error && <LoadError what="the picks" message={error} onRetry={() => setError("")} />}
      {!picks && !error && scopeOk && <Empty>Finding charts for you…</Empty>}
      {picks && picks.recommendations.length === 0 && (
        <Empty>Nothing at {picks.scope || "this level"} would raise your best 50 on {level.label}. Try a harder setting or clear the filter.</Empty>
      )}
      {picks && picks.recommendations.length > 0 && <PickTables picks={picks} onOpen={onOpen} />}
    </>
  );
}

function PickTables({ picks, onOpen }: { picks: PicksData; onOpen?: OpenChart }) {
  const movers = picks.recommendations.filter((r) => r.category !== "near" && r.category !== "try");
  const tries = picks.recommendations.filter((r) => r.category === "try");
  const near = picks.recommendations.filter((r) => r.category === "near");
  const gain = picks.summary?.reachableGain ?? movers.reduce((s, r) => s + r.potential_gain, 0);
  return (
    <>
      {picks.summary?.fallbackFrom && (
        <p className="hint">Nothing on {picks.summary.fallbackFrom} would raise your best 50 yet, so here are the Balanced picks.</p>
      )}
      <section className="ledger">
        <div className="ledger-head">
          <Label info="Charts you've played where a better score raises your rating the most. Target is a score you have a fair shot at, and Gain is the rating you'd get from it.">
            grind these · {movers.length} charts · <b className="gold">+{gain}</b> if you hit every target
          </Label>
        </div>
        {movers.length === 0 ? (
          <Empty>None of your played charts would raise your best 50 here. Try another setting or check the new charts below.</Empty>
        ) : (
          <div className="scroll">
          <table className="tbl">
            <thead>
              <tr>
                <th className="c-n">#</th>
                <th colSpan={2}>Chart</th>
                <th className="c-num">Now</th>
                <th className="c-num">Target</th>
                <th>Rank</th>
                <th className="c-num">Odds</th>
                <th className="c-num">Plays</th>
                <th className="c-num">Gain</th>
              </tr>
            </thead>
            <tbody>
              {movers.map((r, i) => (
                <tr key={`${r.song}|${r.chart_type}|${r.difficulty_type}`}>
                  <td className="c-n">{i + 1}</td>
                  <td className="c-jacket">
                    <Jacket cover={r.cover_url} />
                  </td>
                  <td className="c-title">
                    <TitleLink title={r.song} type={r.chart_type} difficulty={r.difficulty_type} onOpen={onOpen} />
                    <Chip difficulty={r.difficulty_type} level={r.level} constant={r.difficulty} type={r.chart_type} />
                    <span className="sub">
                      {r.estimated ? "not in the chart database yet · constant guessed from its level · " : ""}
                      {r.is_unplayed ? `never played · expect ~${r.expected.toFixed(1)}% first try` : `you usually score ~${r.expected.toFixed(1)}% here`}
                      {r.value_chart_reason?.includes("one run") ? " · your only play here was way under that, so it counts as a dropped run" : ""}
                    </span>
                  </td>
                  <td className="c-num mono" data-l="now">{r.is_unplayed ? <span className="dim">new</span> : pct(r.current_accuracy)}</td>
                  <td className="c-num mono strong" data-l="target">{pct(r.target_accuracy)}</td>
                  <td className="mono" data-l="rank">
                    {r.is_unplayed ? <b>{r.target_rank}</b> : <>{r.current_rank} → <b>{r.target_rank}</b></>}
                  </td>
                  <td className="c-num mono" data-l="odds">{Math.round(r.feasibility * 100)}%</td>
                  <td className="c-num mono dim" data-l="plays">{r.plays > 0 ? r.plays : "?"}</td>
                  <td className="c-num mono gain" data-l="gain">+{r.potential_gain}</td>
                </tr>
              ))}
            </tbody>
          </table>
          </div>
        )}
      </section>

      {tries.length > 0 && (
        <section className="ledger">
          <div className="ledger-head">
            <Label info="Unplayed charts, shown because the grind list is short. Some could add rating on a good first run, and some are practice for patterns you lose points on.">
              worth a first run · {tries.length} charts
            </Label>
          </div>
          <table className="tbl compact">
            <tbody>
              {tries.map((r) => (
                <tr key={`${r.song}|${r.chart_type}|${r.difficulty_type}`}>
                  <td className="c-jacket">
                    <Jacket cover={r.cover_url} size={32} />
                  </td>
                  <td className="c-title">
                    <TitleLink title={r.song} type={r.chart_type} difficulty={r.difficulty_type} onOpen={onOpen} />
                    <Chip difficulty={r.difficulty_type} level={r.level} constant={r.difficulty} type={r.chart_type} />
                    <span className="sub">{(r.value_chart_reason ?? "").replace("never played · ", "")}</span>
                  </td>
                  <td className="c-num mono strong" data-l="aim for">{pct(r.target_accuracy)}</td>
                  <td className="c-num mono" data-l="odds">{Math.round(r.feasibility * 100)}%</td>
                  <td className="c-num mono gain" data-l="gain">{r.potential_gain > 0 ? `+${r.potential_gain}` : <span className="dim">banks</span>}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      )}

      <section className="ledger">
        <div className="ledger-head">
          <Label info="Targets that together get you to the next rating milestone. The % is how far above your usual score they are, so lower is easier.">road to {num(picks.plan.goal)}</Label>
          <span className="mono hint">
            {picks.plan.reached
              ? `covers all +${picks.plan.needed}`
              : `+${picks.plan.total} of the +${picks.plan.needed} needed · ${picks.plan.shortfall} short`}
            {" · "}
            {picks.plan.averageStretch >= 0 ? "+" : ""}
            {picks.plan.averageStretch.toFixed(1)}% above your usual score
          </span>
        </div>
        {picks.plan.steps.length === 0 ? (
          <Empty>No route at this setting yet. Try a different one.</Empty>
        ) : (
          <div className="scroll">
          <table className="tbl">
            <thead>
              <tr>
                <th className="c-n">#</th>
                <th colSpan={2}>Chart</th>
                <th className="c-num">Now</th>
                <th className="c-num">Target</th>
                <th>Rank</th>
                <th className="c-num">Odds</th>
                <th className="c-num">Gain</th>
                <th className="c-num">Total</th>
              </tr>
            </thead>
            <tbody>
              {picks.plan.steps.map((s, i) => (
                <tr key={`${s.option.title}|${s.option.chart_type}|${s.option.difficulty_type}`}>
                  <td className="c-n">{i + 1}</td>
                  <td className="c-jacket">
                    <Jacket cover={s.option.cover} />
                  </td>
                  <td className="c-title">
                    <TitleLink title={s.option.title} type={s.option.chart_type} difficulty={s.option.difficulty_type} onOpen={onOpen} />
                    <Chip difficulty={s.option.difficulty_type} level={s.option.level} constant={s.option.constant} type={s.option.chart_type} />
                    <span className="sub">{s.option.is_unplayed ? "never played" : s.option.plays > 0 ? `${s.option.plays} plays` : "plays unknown"}</span>
                  </td>
                  <td className="c-num mono" data-l="now">{s.option.is_unplayed ? "—" : pct(s.option.current_accuracy)}</td>
                  <td className="c-num mono strong" data-l="target">{pct(s.option.target_accuracy)}</td>
                  <td className="mono" data-l="rank">
                    {s.option.current_rank} → <b>{s.option.target_rank}</b>
                  </td>
                  <td className="c-num mono" data-l="odds">{Math.round(s.option.feasibility * 100)}%</td>
                  <td className="c-num mono gain" data-l="gain">+{s.gain}</td>
                  <td className="c-num mono dim" data-l="total">{s.cumulative}</td>
                </tr>
              ))}
            </tbody>
          </table>
          </div>
        )}
      </section>

      <div className="two-up">
        <section className="ledger">
          <div className="ledger-head">
            <Label info="Unplayed charts where a first try could get into your best 50. Banks means the score counts but won't raise your rating yet.">
              new charts to try · {picks.newWindow[0].toFixed(1)}–{picks.newWindow[1].toFixed(1)}
            </Label>
          </div>
          {picks.newCharts.length === 0 ? (
            <Empty>No unplayed charts in this range.</Empty>
          ) : (
            <table className="tbl compact">
              <tbody>
                {picks.newCharts.map((n) => (
                  <tr key={`${n.title}|${n.chart_type}|${n.difficulty}`}>
                    <td className="c-jacket">
                      <Jacket cover={n.cover} size={32} />
                    </td>
                    <td className="c-title">
                      <TitleLink title={n.title} type={n.chart_type} difficulty={n.difficulty} onOpen={onOpen} />
                      <Chip difficulty={n.difficulty} level={n.level} constant={n.constant} type={n.chart_type} />
                    </td>
                    <td className="c-num mono" data-l="first pass">
                      ~{n.expected_accuracy.toFixed(1)}% <b>{n.expected_rank}</b>
                    </td>
                    <td className="c-num mono dim" data-l="odds of S">{Math.round(n.odds_of_s * 100)}%</td>
                    <td className="c-num mono gain" data-l="gain">{n.rating_gain > 0 ? `+${n.rating_gain}` : <span className="dim">banks</span>}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </section>

        <section className="ledger">
          <div className="ledger-head">
            <Label info="Charts that would get into your best 50 if you score your usual at their level. Needs is the score it takes to get in.">within reach of your best 50</Label>
          </div>
          {near.length === 0 ? (
            <Empty>No charts are close to your best 50 right now.</Empty>
          ) : (
            <table className="tbl compact nojacket">
              <tbody>
                {near.slice(0, 10).map((r) => (
                  <tr key={`${r.song}|${r.chart_type}|${r.difficulty_type}`}>
                    <td className="c-title">
                      <TitleLink title={r.song} type={r.chart_type} difficulty={r.difficulty_type} onOpen={onOpen} />
                      <Chip difficulty={r.difficulty_type} level={r.level} constant={r.difficulty} type={r.chart_type} />
                    </td>
                    <td className="c-num mono" data-l="now">{pct(r.current_accuracy)}</td>
                    <td className="c-num mono dim" data-l="usually">{r.expected ? `${r.expected.toFixed(2)}%` : "—"}</td>
                    <td className="c-num mono" data-l="needs">
                      <b>{pct(r.required_accuracy)}</b>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </section>
      </div>
    </>
  );
}
