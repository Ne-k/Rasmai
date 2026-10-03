"use client";

import { useEffect, useState } from "react";
import { useTranslations } from "next-intl";
import { useLocale } from "@/components/I18n";
import { noteKind } from "@/lib/i18n/traits";
import { ApiError, getJSON, type DifficultyPayload, type JudgementCompare, type LikeYouPayload, type Observed as ObservedData, type ObservedChart } from "./api";
import { Chip, Empty, Jacket, Label, LoadError, TitleLink, pct, type OpenChart } from "./bits";
import "./cohort.css";

/** A payload from one of the cohort routes. The page only asks once the beta is on, so a "not enabled" answer is a race with the switch and shows nothing. */
function useCohort<T>(path: string) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState("");
  const [off, setOff] = useState(false);
  const [tries, setTries] = useState(0);
  useEffect(() => {
    let alive = true;
    setError("");
    getJSON<T>(path)
      .then((d) => alive && setData(d))
      .catch((e: ApiError) => {
        if (!alive) return;
        if (e.status === 404 && e.code === "not_enabled") setOff(true);
        else setError(e.message);
      });
    return () => {
      alive = false;
    };
  }, [path, tries]);
  return { data, error, off, retry: () => setTries((n) => n + 1) };
}

/** The Players tab: both cohort sections, each shown only while its beta switch is on. */
export function Cohort({ on, onOpen }: { on: Record<string, boolean>; onOpen?: OpenChart }) {
  return (
    <>
      {on.likeyou && <LikeYou onOpen={onOpen} />}
      {on.difficulty && <HarderEasier onOpen={onOpen} />}
    </>
  );
}

function LikeYou({ onOpen }: { onOpen?: OpenChart }) {
  const t = useTranslations("cohort");
  const { data, error, off, retry } = useCohort<LikeYouPayload>("/api/me/likeyou");
  if (off) return null;

  let body: React.ReactNode;
  if (error) body = <LoadError what={t("thePlayers")} message={error} onRetry={retry} />;
  else if (!data) body = <Empty>{t("findingLike")}</Empty>;
  else if (data.reason === "not_enough_scores") body = <Empty>{t("thinScores")}</Empty>;
  else if (!data.ready || data.reason === "not_enough_players") body = <Empty>{t("thinPlayers", { n: data.players })}</Empty>;
  else if (data.picks.length === 0) body = <Empty>{t("nothingLike")}</Empty>;
  else
    body = (
      <table className="tbl compact">
        <thead>
          <tr>
            <th colSpan={2}>{t("chart")}</th>
            <th className="c-num">{t("likeYouCol")}</th>
            <th className="c-num">{t("averageCol")}</th>
            <th className="c-num">{t("yoursCol")}</th>
          </tr>
        </thead>
        <tbody>
          {data.picks.map((p) => (
            <tr key={`${p.title}|${p.chartType}|${p.difficulty}`}>
              <td className="c-jacket">
                <Jacket cover={p.cover} size={32} />
              </td>
              <td className="c-title">
                <TitleLink title={p.title} type={p.chartType} difficulty={p.difficulty} onOpen={onOpen} />
                <Chip difficulty={p.difficulty} level={p.level} constant={p.constant} type={p.chartType} />
                <span className="sub">{t("similar", { n: p.neighbours })}</span>
              </td>
              <td className="c-num mono strong" data-l={t("likeYouCol")}>{pct(p.typical)}</td>
              <td className="c-num mono dim" data-l={t("averageCol")}>{p.average === null ? "–" : pct(p.average)}</td>
              <td className="c-num mono" data-l={t("yoursCol")}>
                {p.yours === null ? <span className="dim">{t("notPlayed")}</span> : pct(p.yours)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    );

  return (
    <>
      {data?.judgements && <JudgeCompare data={data.judgements} />}
      <section className="ledger">
        <div className="ledger-head">
          <Label info={t("likeInfo")}>{t("likeTitle")}</Label>
          {data?.ready && data.picks.length > 0 && <span className="mono hint">{t("counted", { n: data.players })}</span>}
        </div>
        {body}
      </section>
    </>
  );
}

/** How far apart two numbers must be before the cell is coloured; closer than this reads as the same. */
const SAME = { per100: 0.05, clean: 0.01 };

/** The person's judgement averages beside the middle of the players like them, a note type to a row. */
function JudgeCompare({ data }: { data: JudgementCompare }) {
  const t = useTranslations("cohort");
  const locale = useLocale();
  const lean = (mine: number, theirs: number, same: number, lowerIsBetter: boolean) =>
    Math.abs(mine - theirs) < same ? "" : (mine < theirs) === lowerIsBetter ? "easier" : "harder";
  return (
    <section className="ledger">
      <div className="ledger-head">
        <Label info={t("judgeInfo")}>{t("judgeTitle")}</Label>
      </div>
      <div className="scroll">
        <table className="tbl compact keep cohort-judge">
          <thead>
            <tr>
              <th rowSpan={2}>{t("judgeNotes")}</th>
              <th className="c-num" colSpan={2}>{t("judgeLost")}</th>
              <th className="c-num" colSpan={2}>{t("judgeClean")}</th>
            </tr>
            <tr>
              <th className="c-num">{t("judgeYou")}</th>
              <th className="c-num">{t("judgeThem")}</th>
              <th className="c-num">{t("judgeYou")}</th>
              <th className="c-num">{t("judgeThem")}</th>
            </tr>
          </thead>
          <tbody>
            {data.types.map((x) => (
              <tr key={x.kind}>
                <td className="mono kind">{noteKind(x.kind, locale)}</td>
                <td className={`c-num mono cohort-dir ${lean(x.per100, x.theirPer100, SAME.per100, true)}`}>{x.per100.toFixed(2)}</td>
                <td className="c-num mono dim">{x.theirPer100.toFixed(2)}</td>
                <td className={`c-num mono cohort-dir ${lean(x.clean, x.theirClean, SAME.clean, false)}`}>{Math.round(x.clean * 100)}%</td>
                <td className="c-num mono dim">{Math.round(x.theirClean * 100)}%</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {data.theirLostPerPlay !== null && (
        <p className="hint cohort-note">{t("judgeLostPlay", { you: data.lostPerPlay.toFixed(2), them: data.theirLostPerPlay.toFixed(2) })}</p>
      )}
      {data.lateShare !== null && data.theirLateShare !== null && (
        <p className="hint">{t("judgeLate", { you: Math.round(data.lateShare * 100), them: Math.round(data.theirLateShare * 100) })}</p>
      )}
      <p className="hint">{t("judgeNote", { n: data.players, you: data.plays })}</p>
    </section>
  );
}

const share = (v: number) => `${Math.round(v * 100)}%`;

/** How often the people who played a chart got an SS, beside how often players of their rating do on its level, and which way that leans. */
export function Observed({ rate, expected, players, lean }: ObservedData) {
  const t = useTranslations("cohort");
  return (
    <p className="hint chart-observed" title={t("observedInfo")}>
      <span className="mono">{t("observed", { rate: share(rate), expected: share(expected), n: players })}</span>
      {" · "}
      <span className={`cohort-dir ${lean}`}>{t(`dir.${lean}`)}</span>
    </p>
  );
}

function Lean({ rows, kind, onOpen }: { rows: ObservedChart[]; kind: "harder" | "easier"; onOpen?: OpenChart }) {
  const t = useTranslations("cohort");
  return (
    <div>
      <p className="label cohort-sub">{t(`${kind}Title`)}</p>
      {rows.length === 0 ? (
        <Empty>{t(`${kind}None`)}</Empty>
      ) : (
        <table className="tbl compact">
          <thead>
            <tr>
              <th colSpan={2}>{t("chart")}</th>
              <th className="c-num">{t("rateCol")}</th>
              <th className="c-num">{t("expectedCol")}</th>
              <th className="c-num">{t("averageCol")}</th>
              <th className="c-num">{t("playersCol")}</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={`${r.title}|${r.chartType}|${r.difficulty}`}>
                <td className="c-jacket">
                  <Jacket cover={r.cover} size={32} />
                </td>
                <td className="c-title">
                  <TitleLink title={r.title} type={r.chartType} difficulty={r.difficulty} onOpen={onOpen} />
                  <Chip difficulty={r.difficulty} level={r.level} type={r.chartType} />
                </td>
                <td className={`c-num mono cohort-dir ${kind}`} data-l={t("rateCol")}>
                  <b>{share(r.rate)}</b>
                </td>
                <td className="c-num mono dim" data-l={t("expectedCol")}>{share(r.expected)}</td>
                <td className="c-num mono dim" data-l={t("averageCol")}>{r.average === null ? "–" : pct(r.average)}</td>
                <td className="c-num mono dim" data-l={t("playersCol")}>{r.players}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}

/** The charts that play furthest from their listed constant, harder on one side and easier on the other. */
function HarderEasier({ onOpen }: { onOpen?: OpenChart }) {
  const t = useTranslations("cohort");
  const [open, setOpen] = useState(true);
  return (
    <section className="ledger">
      <div className="ledger-head">
        <Label info={t("diffInfo")}>{t("diffTitle")}</Label>
        <button type="button" className="linkish" aria-expanded={open} onClick={() => setOpen(!open)}>
          {open ? t("hide") : t("show")}
        </button>
      </div>
      {open && <Lists onOpen={onOpen} />}
    </section>
  );
}

function Lists({ onOpen }: { onOpen?: OpenChart }) {
  const t = useTranslations("cohort");
  const { data, error, off, retry } = useCohort<DifficultyPayload>("/api/me/difficulty");
  if (off) return null;
  if (error) return <LoadError what={t("theDifficulty")} message={error} onRetry={retry} />;
  if (!data) return <Empty>{t("findingDiff")}</Empty>;
  if (!data.ready) return <Empty>{t("thinPlayers", { n: data.players })}</Empty>;
  return (
    <>
      <p className="hint cohort-note">{t("diffNote", { n: data.players })}</p>
      <div className="two-up">
        <Lean rows={data.harder} kind="harder" onOpen={onOpen} />
        <Lean rows={data.easier} kind="easier" onOpen={onOpen} />
      </div>
    </>
  );
}
