"use client";

import { useTranslations } from "next-intl";
import type { Observed as ObservedData } from "./api";
import "./cohort.css";

const share = (v: number) => `${Math.round(v * 100)}%`;

/** How often the people who played a chart got an SS, beside how often players of their rating do on its level. Hover for why it isn't hard data. */
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
