"use client";

import { useMemo } from "react";
import { useTranslations } from "next-intl";
import { type ChartRow, type Overview } from "./api";
import { Empty, Label, LoadError, num, pct } from "./bits";
import { SkillCurve } from "./SkillCurve";
import { Sparkline } from "./Sparkline";
import { levelValue } from "./Best50";

const RANK_ORDER = ["SSS+", "SSS", "SS+", "SS", "S+", "S", "AAA", "AA", "A", "BBB", "BB", "B", "C", "D"];

export function OverviewTab({ me, charts, chartsError, onRetry }: { me: Overview; charts: ChartRow[] | null; chartsError?: string; onRetry?: () => void }) {
  const t = useTranslations("overviewTab");
  const d = useTranslations("dash");
  const stats = useMemo(() => {
    if (!charts) return null;
    const upper = charts.filter((c) => ["expert", "master", "remaster"].includes(c.difficulty));
    const ranks: Record<string, number> = {};
    for (const c of upper) ranks[c.rank] = (ranks[c.rank] ?? 0) + 1;
    const fcPlus = charts.filter((c) => c.fc === "FC+" || c.fc === "AP" || c.fc === "AP+").length;
    const fc = charts.filter((c) => c.fc === "FC").length;
    const ap = charts.filter((c) => c.fc === "AP" || c.fc === "AP+").length;
    const fsPlus = charts.filter((c) => c.fs === "FS+" || c.fs === "FDX" || c.fs === "FDX+").length;
    const levels = new Map<string, { n: number; sum: number }>();
    for (const c of upper) {
      const e = levels.get(c.level) ?? { n: 0, sum: 0 };
      e.n += 1;
      e.sum += c.accuracy;
      levels.set(c.level, e);
    }
    return { upper: upper.length, ranks, fc, fcPlus, ap, fsPlus, levels };
  }, [charts]);
  const prof = me.analysis?.profile;
  const habits = prof?.habits;
  const b50 = me.analysis?.best50;
  return (
    <>
      <Sparkline points={me.history ?? []} />
      {chartsError ? <LoadError what={d("yourCharts")} message={chartsError} onRetry={onRetry} /> : null}
      {prof?.curve && prof.curve.length > 1 && (
        <SkillCurve
          curve={prof.curve}
          charts={charts}
          comfort={prof.comfortConstant}
          reach={prof.reachConstant}
          playedCeiling={prof.playedCeiling}
        />
      )}
      <div className="two-up">
        <section className="ledger">
          <div className="ledger-head">
            <Label info={t("howInfo")}>{t("how")}</Label>
          </div>
          <dl className="facts">
            <dt>{t("comfort")}</dt>
            <dd className="mono">{prof ? prof.comfortConstant.toFixed(1) : "—"}</dd>
            <dt>{t("reach")}</dt>
            <dd className="mono">{prof ? prof.reachConstant.toFixed(1) : "—"}</dd>
            <dt>{t("hardestS")}</dt>
            <dd className="mono">{prof ? prof.hardestS.toFixed(1) : "—"}</dd>
            {habits?.age ? (
              <>
                <dt>{t("age")}</dt>
                <dd className="mono">
                  {t("ageValue", { years: habits.age.medianYears.toFixed(1), fresh: Math.round(habits.age.freshShare * 100) })}
                </dd>
              </>
            ) : null}
            {habits?.rerates ? (
              <>
                <dt>{t("rerates")}</dt>
                <dd className="mono">
                  {t("reratesValue", { rating: `${habits.rerates.rating >= 0 ? "+" : ""}${habits.rerates.rating}`, charts: habits.rerates.charts })}
                </dd>
              </>
            ) : null}
            {habits?.notes ? (
              <>
                <dt>{t("notes")}</dt>
                <dd className="mono">{num(habits.notes.notes)}</dd>
              </>
            ) : null}
            {habits?.warmUp ? (
              <>
                <dt>{t("warmUp")}</dt>
                <dd className="mono">
                  {t("warmUpValue", { gap: Math.abs(habits.warmUp.gap).toFixed(2), colder: String(habits.warmUp.colder) })}
                </dd>
              </>
            ) : null}
            <dt>{t("scored")}</dt>
            <dd className="mono">{num(me.snapshot?.charts)}</dd>
            <dt>{t("upper")}</dt>
            <dd className="mono">{stats ? num(stats.upper) : "—"}</dd>
            <dt>{t("fullCombos")}</dt>
            <dd className="mono">{stats ? t("fullCombosValue", { all: num(stats.fc + stats.fcPlus), ap: num(stats.ap) }) : "—"}</dd>
            <dt>{t("fullSync")}</dt>
            <dd className="mono">{stats ? num(stats.fsPlus) : "—"}</dd>
            <dt>{t("reachable")}</dt>
            <dd className="mono gain">{me.analysis?.reachableGain != null ? `+${me.analysis.reachableGain}` : "—"}</dd>
          </dl>
        </section>
        <section className="ledger">
          <div className="ledger-head">
            <Label info={t("cutoffsInfo")}>{t("cutoffs")}</Label>
          </div>
          <dl className="facts">
            <dt>{t("newPool")}</dt>
            <dd className="mono">
              {b50 ? t("entersAt", { total: num(b50.newTotal), cutoff: b50.newCutoff }) : "—"}
              {b50 && b50.newSlotsOpen > 0 ? t("open", { n: b50.newSlotsOpen }) : ""}
            </dd>
            <dt>{t("oldPool")}</dt>
            <dd className="mono">
              {b50 ? t("entersAt", { total: num(b50.oldTotal), cutoff: b50.oldCutoff }) : "—"}
              {b50 && b50.oldSlotsOpen > 0 ? t("open", { n: b50.oldSlotsOpen }) : ""}
            </dd>
          </dl>
          <div className="ledger-head">
            <Label info={t("ranksInfo")}>{t("ranks")}</Label>
          </div>
          {stats ? (
            <ul className="bars">
              {RANK_ORDER.filter((r) => stats.ranks[r]).map((r) => (
                <li key={r}>
                  <span className="mono k">{r}</span>
                  <span className="bar">
                    <span style={{ width: `${(100 * stats.ranks[r]) / stats.upper}%` }} />
                  </span>
                  <span className="mono v">{stats.ranks[r]}</span>
                </li>
              ))}
            </ul>
          ) : (
            <Empty>{d("loading")}</Empty>
          )}
        </section>
      </div>
      {stats && stats.levels.size > 0 && (
        <section className="ledger">
          <div className="ledger-head">
            <Label info={t("levelsInfo")}>{t("levels")}</Label>
          </div>
          <table className="tbl compact levels keep">
            <tbody>
              {[...stats.levels.entries()]
                .sort((a, b) => levelValue(b[0]) - levelValue(a[0]))
                .map(([level, e]) => (
                  <tr key={level}>
                    <td className="mono strong">{level}</td>
                    <td className="c-num mono dim">{t("charts", { n: e.n })}</td>
                    <td className="c-bar">
                      <span className="bar">
                        <span style={{ width: `${Math.max(0, Math.min(100, ((e.sum / e.n - 80) * 100) / 21))}%` }} />
                      </span>
                    </td>
                    <td className="c-num mono">{pct(e.sum / e.n)}</td>
                  </tr>
                ))}
            </tbody>
          </table>
        </section>
      )}
    </>
  );
}
