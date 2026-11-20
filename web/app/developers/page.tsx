import type { Metadata } from "next";
import { getTranslations } from "next-intl/server";
import { places } from "./docs/parts";

// a page of the documentation, under /docs/, and the words that say what it is for
const DOCS = [
  ["", "start"],
  ["oauth2/", "oauth2"],
  ["oauth2/#no-website", "bots"],
  ["sign-in/", "signIn"],
  ["extension/", "extension"],
] as const;
const STEPS = ["step1", "step2", "step3", "step4"] as const;

export async function generateMetadata(): Promise<Metadata> {
  const t = await getTranslations("developers.home");
  // unlike a developer's own applications, the front page is for anyone to find
  return { robots: { index: true, follow: true }, description: t("metaDescription") };
}

export default async function DevelopersHome() {
  const t = await getTranslations("developers.home");
  const { site, base } = await places();
  return (
    <main className="dp-home">
      <div className="dp-top">
        <div className="dp-doc">
          <h1>{t("title")}</h1>
          <p className="dp-lede">{t("lede")}</p>
          <div className="btn-row">
            <a className="button pink" href={`${base}/applications/`}>{t("apps")}</a>
            <a className="button ghost" href={`${base}/docs/`}>{t("docs")}</a>
          </div>
        </div>
        <div className="shots">
          <figure>
            <img src="/helper/approval.png" width={420} height={340} alt="" decoding="async" />
            <figcaption>{t("shot")}</figcaption>
          </figure>
        </div>
      </div>
      <div className="dp-doc">
        <h2>{t("stepsTitle")}</h2>
        <ol>
          {STEPS.map((step) => (
            <li key={step}>{t(step)}</li>
          ))}
        </ol>
        <p>{t("flow")}</p>

        <h2>{t("docsTitle")}</h2>
        <ul className="dp-pages">
          {DOCS.map(([path, key]) => (
            <li key={key}>
              <a href={`${base}/docs/${path}`}>
                <b>{t(`${key}.name`)}</b>
                <span>{t(`${key}.about`)}</span>
              </a>
            </li>
          ))}
        </ul>

        <h2>{t("needsTitle")}</h2>
        <p>{t.rich("needs", { ext: (c) => <a href={`${site}/extension/`}>{c}</a> })}</p>
      </div>
    </main>
  );
}
