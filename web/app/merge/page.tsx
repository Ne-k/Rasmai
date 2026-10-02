import type { Metadata } from "next";
import { cookies } from "next/headers";
import { redirect } from "next/navigation";
import { getTranslations } from "next-intl/server";
import { Shell } from "@/components/Shell";
import { ProviderIcon } from "@/components/ProviderIcon";
import { readPending, type Summary } from "@/lib/pending";
import "../welcome/onboarding.css";

export async function generateMetadata(): Promise<Metadata> {
  const t = await getTranslations("merge");
  return { title: t("metaTitle"), robots: { index: false } };
}

export default async function MergePage() {
  const merge = readPending(await cookies())?.merge;
  if (!merge) redirect("/me/");
  const t = await getTranslations("merge");
  const footer = await getTranslations("footer");

  const card = (keep: "from" | "to", label: string, s: Summary) => (
    <div className="ob-acct">
      <div className="ob-label" id={`acct-${keep}`}>
        {keep === "to" && <ProviderIcon provider="discord" size={14} />}
        {label}
      </div>
      <div className="ob-player" id={`player-${keep}`}>{s.player}</div>
      <div className="ob-acct-meta">
        <div className="readout">
          <span className="lbl">{t("ratingLabel")}</span>
          <span className="val">{s.rating ?? "-"}</span>
        </div>
        <span className="ob-tag">
          <span>{t("regionLabel")}</span> {s.region ? s.region.toUpperCase() : "-"}
        </span>
      </div>
      <button className="button pink" type="submit" name="keep" value={keep} aria-describedby={`acct-${keep} player-${keep}`}>
        {t("keepThis")}
      </button>
    </div>
  );

  return (
    <Shell tag="merge" lit={2} footLeft={t("nothingChanges")} footRight={footer("notAffiliated")}>
      <h1>{t.rich("title", { em: (c) => <em>{c}</em> })}</h1>
      <p className="lede">{t("lede")}</p>

      <h2 className="ob-head">{t("choiceTitle")}</h2>
      <p className="ob-warn">{t.rich("explain", { b: (c) => <b>{c}</b> })}</p>

      <form className="ob-pick" method="post" action="/auth/merge">
        {card("from", t("fromLabel"), merge.fromSummary)}
        <span className="ob-or" aria-hidden="true">{t("or")}</span>
        {card("to", t("toLabel"), merge.toSummary)}
      </form>
      <p className="hint ob-cancel">
        <a href="/me/">{t("cancel")}</a> · {t("cancelNote")}
      </p>
    </Shell>
  );
}
