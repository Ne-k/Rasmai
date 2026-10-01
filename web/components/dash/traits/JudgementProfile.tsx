"use client";

import { useTranslations } from "next-intl";
import { useLocale } from "@/components/I18n";
import { noteKind } from "@/lib/i18n/traits";
import type { JudgementProfileData } from "../api";
import { Empty, Label } from "../bits";

export function JudgementProfile({ data }: { data: JudgementProfileData | null }) {
  const t = useTranslations("judgeTab");
  const locale = useLocale();
  const weak = data?.types.find((x) => x.kind === data.weak);
  const share = data?.lateShare ?? null;
  const timing =
    share === null
      ? ""
      : share >= 0.6
        ? t("late", { n: Math.round(share * 100) })
        : share <= 0.4
          ? t("early", { n: Math.round((1 - share) * 100) })
          : t("even");
  return (
    <section className="ledger">
      <div className="ledger-head">
        <Label info={t("info")}>{t("title")}</Label>
        <span className="mono hint">{data ? t("summary", { plays: data.plays, lost: data.lostPerPlay.toFixed(2) }) : ""}</span>
      </div>
      {!data ? (
        <Empty>{t("needs")}</Empty>
      ) : (
        <div className="two-up">
          {/* six columns will not fit a phone, and this table keeps its shape rather than becoming
              cards, so it scrolls sideways inside its own box instead of pushing the page out */}
          <div className="scroll">
          <table className="tbl compact keep judge-profile">
            <thead>
              <tr>
                <th>{t("notes")}</th>
                <th className="c-num">{t("ofNotes")}</th>
                <th className="c-num">{t("worth")}</th>
                <th className="c-num">{t("ofLoss")}</th>
                <th className="c-num">{t("per100")}</th>
                <th className="c-num">{t("clean")}</th>
              </tr>
            </thead>
            <tbody>
              {data.types.map((x) => (
                <tr key={x.kind} data-kind={x.kind} className={x.kind === data.weak ? "weak" : ""}>
                  <td className="mono kind">{noteKind(x.kind, locale)}</td>
                  <td className="c-num mono">{Math.round(x.share * 100)}%</td>
                  <td className="c-num mono dim">{Math.round((x.stakeShare ?? x.share) * 100)}%</td>
                  <td className="c-num mono">{Math.round(x.lossShare * 100)}%</td>
                  <td className="c-num mono">{x.per100.toFixed(2)}</td>
                  <td className="c-num mono dim">{Math.round(x.clean * 100)}%</td>
                </tr>
              ))}
            </tbody>
          </table>
          </div>
          <div>
            <p className="hint">
              {weak
                ? t("weak", { kind: locale === "ja" ? noteKind(weak.kind, locale) : `${weak.kind[0].toUpperCase()}${weak.kind.slice(1)}`, loss: Math.round(weak.lossShare * 100), worth: Math.round((weak.stakeShare ?? weak.share) * 100) })
                : t("noWeak")}
            </p>
            {Boolean(data.bonusPerPlay) && (
              <p className="hint">{t("bonus", { per: (data.bonusPerPlay ?? 0).toFixed(2), share: Math.round((data.bonusShare ?? 0) * 100) })}</p>
            )}
            <ul className="bars">
              <li>
                <span>{t("fast")}</span>
                <span className="bar">
                  <span style={{ width: `${data.fast + data.late ? (100 * data.fast) / (data.fast + data.late) : 0}%` }} />
                </span>
                <span className="v">{data.fast}</span>
              </li>
              <li>
                <span>{t("lateBar")}</span>
                <span className="bar">
                  <span style={{ width: `${data.fast + data.late ? (100 * data.late) / (data.fast + data.late) : 0}%` }} />
                </span>
                <span className="v">{data.late}</span>
              </li>
            </ul>
            {timing ? <p className="hint">{timing}</p> : null}
          </div>
        </div>
      )}
    </section>
  );
}
