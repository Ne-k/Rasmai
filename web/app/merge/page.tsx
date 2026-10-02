import type { Metadata } from "next";
import { cookies } from "next/headers";
import { redirect } from "next/navigation";
import { getTranslations } from "next-intl/server";
import { Shell } from "@/components/Shell";
import { readPending, type Summary } from "@/lib/pending";

export async function generateMetadata(): Promise<Metadata> {
  const t = await getTranslations("merge");
  return { title: t("metaTitle"), robots: { index: false } };
}

export default async function MergePage() {
  const merge = readPending(await cookies())?.merge;
  if (!merge) redirect("/me/");
  const t = await getTranslations("merge");
  const footer = await getTranslations("footer");

  const card = (label: string, s: Summary) => (
    <div className="stat">
      <div className="k">{label}</div>
      <div className="v" style={{ fontSize: 22, overflowWrap: "anywhere" }}>{s.player}</div>
      <p className="hint" style={{ marginTop: 6 }}>
        {t("ratingLabel")} {s.rating ?? "-"} · {t("regionLabel")} {s.region ? s.region.toUpperCase() : "-"}
      </p>
    </div>
  );

  return (
    <Shell tag="merge" lit={2} footLeft={t("nothingChanges")} footRight={footer("notAffiliated")}>
      <h1>{t.rich("title", { em: (c) => <em>{c}</em> })}</h1>
      <p className="lede">{t("lede")}</p>

      <div className="card-row">
        {card(t("fromLabel"), merge.fromSummary)}
        {card(t("toLabel"), merge.toSummary)}
      </div>

      <h2 className="subhead">{t("choiceTitle")}</h2>
      <p className="lede" style={{ marginTop: 8 }}>{t.rich("explain", { b: (c) => <b>{c}</b> })}</p>

      <form method="post" action="/auth/merge">
        <div className="btn-row">
          <button className="button pink" type="submit" name="keep" value="from">{t("keepFrom")}</button>
          <button className="button pink" type="submit" name="keep" value="to">{t("keepTo")}</button>
        </div>
      </form>
      <p className="hint" style={{ marginTop: 14 }}>
        <a href="/me/">{t("cancel")}</a> · {t("cancelNote")}
      </p>
    </Shell>
  );
}
