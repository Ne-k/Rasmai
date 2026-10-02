import type { Metadata } from "next";
import { cookies } from "next/headers";
import { redirect } from "next/navigation";
import { getTranslations } from "next-intl/server";
import { Shell } from "@/components/Shell";
import { ProviderIcon } from "@/components/ProviderIcon";
import { readPending } from "@/lib/pending";
import { POLICY_VERSION } from "@/lib/policy";
import "./onboarding.css";

export async function generateMetadata(): Promise<Metadata> {
  const t = await getTranslations("welcome");
  return { title: t("metaTitle"), description: t("metaDescription"), robots: { index: false } };
}

const MEANS = ["i01", "i02", "i03", "i04", "i05", "i06"] as const;
const DOCS = [
  ["privacy", "/privacy/"],
  ["terms", "/terms/"],
] as const;

export default async function WelcomePage() {
  const pending = readPending(await cookies());
  if (!pending) redirect("/me/");
  if (pending.merge) redirect("/merge/");
  const t = await getTranslations("welcome");
  const footer = await getTranslations("footer");
  const hasDiscord = pending.identities.some((i) => i.provider === "discord");

  return (
    <Shell tag="welcome" lit={2} footLeft={t("nothingCreated")} footRight={footer("notAffiliated")}>
      <h1>{t.rich("title", { em: (c) => <em>{c}</em> })}</h1>
      <p className="lede">{t("lede")}</p>
      <div className="ob-who">
        <span className="ob-label">{t("who")}</span>
        {pending.identities.map((i) => (
          <span key={i.provider} className="ob-chip">
            <span className={`ob-mark ${i.provider}`}>
              <ProviderIcon provider={i.provider} size={16} />
            </span>
            {i.name && <b>{i.name}</b>}
            <span className="ob-chip-via">{t(`providers.${i.provider}`)}</span>
          </span>
        ))}
      </div>

      <div className="ob-grid">
        <section>
          <h2 className="ob-head">{t("meansTitle")}</h2>
          <dl className="ob-means">
            {MEANS.map((key) => (
              <div key={key}>
                <dt>{t(`meansTerms.${key}`)}</dt>
                <dd>{t(`means.${key}`)}</dd>
              </div>
            ))}
          </dl>
        </section>

        <section className="ob-side">
          <p className="hint">{t("readFirst")}</p>
          <div className="ob-docs">
            {DOCS.map(([key, href]) => (
              <a key={key} className="ob-doc" href={href} target="_blank" rel="noopener noreferrer">
                <span className="ob-doc-name">
                  {t(`docs.${key}`)}
                  <span className="ob-sr"> {t("docs.newTab")}</span>
                </span>
                <span className="ob-doc-date">{t("docs.updated", { date: POLICY_VERSION })}</span>
                <svg className="ob-doc-out" width="14" height="14" viewBox="0 0 14 14" aria-hidden="true" focusable="false">
                  <path d="M5 2H2v10h10V9M8 2h4v4M12 2 6.5 7.5" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
                </svg>
              </a>
            ))}
          </div>

          <form className="ob-form" method="post" action="/auth/accept">
            <label className="ob-agree">
              <input type="checkbox" name="terms" required />
              <span>{t("agree")}</span>
            </label>
            <button className="button pink ob-go" type="submit">{t("create")}</button>
            <p className="hint">{t("expires")}</p>
          </form>
        </section>
      </div>

      {!hasDiscord && (
        <div className="ob-alt">
          <span className="ob-mark discord big">
            <ProviderIcon provider="discord" size={22} />
          </span>
          <div>
            <b>{t("alreadyTitle")}</b>
            <p>{t("alreadyBody")}</p>
            <a className="button ghost" href="/auth/discord?keep=pending">{t("already")}</a>
          </div>
        </div>
      )}
    </Shell>
  );
}
