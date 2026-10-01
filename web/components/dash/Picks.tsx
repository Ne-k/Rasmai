import { useEffect, useState } from "react";
import { useTranslations } from "next-intl";
import { getJSON, type Picks as PicksData } from "./api";
import { Chip, Empty, Jacket, Label, LoadError, num, pct } from "./bits";
import { TitleLink, type OpenChart } from "./bits";

const LEVELS = ["easy", "balanced", "hard", "extreme"];

const CHART_LEVELS = ["15", "14+", "14", "13+", "13", "12+", "12", "11+", "11", "10+", "10", "9+", "9", "8+", "8", "7+", "7"];
/** A level (13+), one constant (13.2) or a range (13.0-13.4); the server reads the same forms. */
const SCOPE_OK = /^(\d{1,2}\+?|\d{1,2}\.\d|\d{1,2}(\.\d)?\s*-\s*\d{1,2}(\.\d)?)$/;

export function Picks({ initial, onOpen }: { initial: string; onOpen?: OpenChart }) {
  const t = useTranslations("picksTab");
  const ch = useTranslations("challenge");
  const [challenge, setChallenge] = useState(LEVELS.includes(initial) ? initial : "balanced");
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

  const level = { label: ch(`label.${challenge}` as never), note: ch(`picksNote.${challenge}` as never) };
  return (
    <>
      <div className="row-between">
        <div className="seg" role="group" aria-label={t("howHard")}>
          {LEVELS.map((l) => (
            <button key={l} type="button" className={l === challenge ? "on" : ""} aria-pressed={l === challenge} onClick={() => setChallenge(l)}>
              {ch(`label.${l}` as never)}
            </button>
          ))}
        </div>
        <span className="hint">
          {level.note}
          {picks?.scope ? t("filtered", { scope: picks.scope }) : ""}
        </span>
      </div>
      <div className="filters scope-filters">
        <select value={chartLevel} onChange={(e) => setChartLevel(e.target.value)} aria-label={t("onlyLevel")} disabled={Boolean(typed)}>
          <option value="">{t("anyLevel")}</option>
          {CHART_LEVELS.map((l) => (
            <option key={l} value={l}>
              {t("level", { l })}
            </option>
          ))}
        </select>
        <input
          className="search scope-constant"
          type="text"
          role="searchbox"
          value={constant}
          placeholder={t("constantPlaceholder")}
          aria-label={t("onlyConstant")}
          onChange={(e) => setConstant(e.target.value)}
        />
        {!scopeOk && <span className="hint">{t("scopeHint")}</span>}
      </div>
      {error && <LoadError what={t("thePicks")} message={error} onRetry={() => setError("")} />}
      {!picks && !error && scopeOk && <Empty>{t("finding")}</Empty>}
      {picks && picks.recommendations.length === 0 && (
        <Empty>{t("nothing", { scope: picks.scope || "none", level: level.label })}</Empty>
      )}
      {picks && picks.recommendations.length > 0 && <PickTables picks={picks} onOpen={onOpen} />}
    </>
  );
}

function PickTables({ picks, onOpen }: { picks: PicksData; onOpen?: OpenChart }) {
  const t = useTranslations("picksTab");
  const c = useTranslations("cols");
  const ch = useTranslations("challenge");
  const movers = picks.recommendations.filter((r) => r.category !== "near" && r.category !== "try");
  const tries = picks.recommendations.filter((r) => r.category === "try");
  const near = picks.recommendations.filter((r) => r.category === "near");
  const gain = picks.summary?.reachableGain ?? movers.reduce((s, r) => s + r.potential_gain, 0);
  return (
    <>
      {picks.summary?.fallbackFrom && (
        <p className="hint">{t("fallback", { from: ch.has(`label.${picks.summary.fallbackFrom}` as never) ? ch(`label.${picks.summary.fallbackFrom}` as never) : picks.summary.fallbackFrom })}</p>
      )}
      <section className="ledger">
        <div className="ledger-head">
          <Label info={t("grindInfo")}>
            {t("grind", { n: movers.length })}<b className="gold">+{gain}</b>{t("everyTarget")}
          </Label>
        </div>
        {movers.length === 0 ? (
          <Empty>{t("noMovers")}</Empty>
        ) : (
          <div className="scroll">
          <table className="tbl">
            <thead>
              <tr>
                <th className="c-n">#</th>
                <th colSpan={2}>{c("chart")}</th>
                <th className="c-num">{c("now")}</th>
                <th className="c-num">{c("target")}</th>
                <th>{c("rank")}</th>
                <th className="c-num">{c("odds")}</th>
                <th className="c-num">{c("plays")}</th>
                <th className="c-num">{c("gain")}</th>
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
                      {r.estimated ? t("estimated") : ""}
                      {r.is_unplayed ? t("neverExpect", { n: r.expected.toFixed(1) }) : t("usually", { n: r.expected.toFixed(1) })}
                      {r.value_chart_reason?.includes("one run") ? t("dropped") : ""}
                    </span>
                  </td>
                  <td className="c-num mono" data-l={c("now")}>{r.is_unplayed ? <span className="dim">{t("new")}</span> : pct(r.current_accuracy)}</td>
                  <td className="c-num mono strong" data-l={c("target")}>{pct(r.target_accuracy)}</td>
                  <td className="mono" data-l={c("rank")}>
                    {r.is_unplayed ? <b>{r.target_rank}</b> : <>{r.current_rank} → <b>{r.target_rank}</b></>}
                  </td>
                  <td className="c-num mono" data-l={c("odds")}>{Math.round(r.feasibility * 100)}%</td>
                  <td className="c-num mono dim" data-l={c("plays")}>{r.plays > 0 ? r.plays : "?"}</td>
                  <td className="c-num mono gain" data-l={c("gain")}>+{r.potential_gain}</td>
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
            <Label info={t("triesInfo")}>
              {t("tries", { n: tries.length })}
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
                  <td className="c-num mono strong" data-l={c("aimFor")}>{pct(r.target_accuracy)}</td>
                  <td className="c-num mono" data-l={c("odds")}>{Math.round(r.feasibility * 100)}%</td>
                  <td className="c-num mono gain" data-l={c("gain")}>{r.potential_gain > 0 ? `+${r.potential_gain}` : <span className="dim">{t("banks")}</span>}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      )}

      <section className="ledger">
        <div className="ledger-head">
          <Label info={t("roadInfo")}>{t("road", { goal: num(picks.plan.goal) })}</Label>
          <span className="mono hint">
            {picks.plan.reached
              ? t("covers", { n: picks.plan.needed })
              : t("partway", { total: picks.plan.total, needed: picks.plan.needed, short: picks.plan.shortfall })}
            {" · "}
            {t("stretch", { n: `${picks.plan.averageStretch >= 0 ? "+" : ""}${picks.plan.averageStretch.toFixed(1)}` })}
          </span>
        </div>
        {picks.plan.steps.length === 0 ? (
          <Empty>{t("noRoute")}</Empty>
        ) : (
          <div className="scroll">
          <table className="tbl">
            <thead>
              <tr>
                <th className="c-n">#</th>
                <th colSpan={2}>{c("chart")}</th>
                <th className="c-num">{c("now")}</th>
                <th className="c-num">{c("target")}</th>
                <th>{c("rank")}</th>
                <th className="c-num">{c("odds")}</th>
                <th className="c-num">{c("gain")}</th>
                <th className="c-num">{c("total")}</th>
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
                    <span className="sub">{s.option.is_unplayed ? t("neverPlayed") : s.option.plays > 0 ? t("plays", { n: s.option.plays }) : t("playsUnknown")}</span>
                  </td>
                  <td className="c-num mono" data-l={c("now")}>{s.option.is_unplayed ? "—" : pct(s.option.current_accuracy)}</td>
                  <td className="c-num mono strong" data-l={c("target")}>{pct(s.option.target_accuracy)}</td>
                  <td className="mono" data-l={c("rank")}>
                    {s.option.current_rank} → <b>{s.option.target_rank}</b>
                  </td>
                  <td className="c-num mono" data-l={c("odds")}>{Math.round(s.option.feasibility * 100)}%</td>
                  <td className="c-num mono gain" data-l={c("gain")}>+{s.gain}</td>
                  <td className="c-num mono dim" data-l={c("total")}>{s.cumulative}</td>
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
            <Label info={t("newInfo")}>
              {t("newCharts", { from: picks.newWindow[0].toFixed(1), to: picks.newWindow[1].toFixed(1) })}
            </Label>
          </div>
          {picks.newCharts.length === 0 ? (
            <Empty>{t("noNew")}</Empty>
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
                    <td className="c-num mono" data-l={c("firstPass")}>
                      ~{n.expected_accuracy.toFixed(1)}% <b>{n.expected_rank}</b>
                    </td>
                    <td className="c-num mono dim" data-l={c("oddsS")}>{Math.round(n.odds_of_s * 100)}%</td>
                    <td className="c-num mono gain" data-l={c("gain")}>{n.rating_gain > 0 ? `+${n.rating_gain}` : <span className="dim">{t("banks")}</span>}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </section>

        <section className="ledger">
          <div className="ledger-head">
            <Label info={t("nearInfo")}>{t("near")}</Label>
          </div>
          {near.length === 0 ? (
            <Empty>{t("noNear")}</Empty>
          ) : (
            <table className="tbl compact nojacket">
              <tbody>
                {near.slice(0, 10).map((r) => (
                  <tr key={`${r.song}|${r.chart_type}|${r.difficulty_type}`}>
                    <td className="c-title">
                      <TitleLink title={r.song} type={r.chart_type} difficulty={r.difficulty_type} onOpen={onOpen} />
                      <Chip difficulty={r.difficulty_type} level={r.level} constant={r.difficulty} type={r.chart_type} />
                    </td>
                    <td className="c-num mono" data-l={c("now")}>{pct(r.current_accuracy)}</td>
                    <td className="c-num mono dim" data-l={c("usually")}>{r.expected ? `${r.expected.toFixed(2)}%` : "—"}</td>
                    <td className="c-num mono" data-l={c("needs")}>
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
