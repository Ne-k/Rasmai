import type { Metadata } from "next";
import { Shell } from "@/components/Shell";
import { Walkthrough } from "@/components/Walkthrough";
import { getTranslations } from "next-intl/server";

export async function generateMetadata(): Promise<Metadata> {
  const t = await getTranslations("link");
  return {
    title: t("metaTitle"),
    description: t("metaDescription"),
    alternates: { canonical: "/link/" },
    openGraph: { title: `${t("metaTitle")} · Rasmai`, description: t("metaDescription"), url: "/link/", images: ["/opengraph-image"] },
  };
}

export default async function LinkPage() {
  const t = await getTranslations("link");
  const footer = await getTranslations("footer");
  const tags = {
    b: (c: React.ReactNode) => <b>{c}</b>,
    em: (c: React.ReactNode) => <em>{c}</em>,
    code: (c: React.ReactNode) => <code>{c}</code>,
    aime: (c: React.ReactNode) => <a href="https://my-aime.net/en/">{c}</a>,
    dash: (c: React.ReactNode) => <a href="/me/">{c}</a>,
  };
  return (
    <Shell tag="link" lit={1} footLeft={footer("notAffiliated")}>
      <h1>{t.rich("title", tags)}</h1>
      <p className="lede">{t("lede")}</p>

      <section className="step walk-step">
        <div className="n" aria-hidden="true">
          ▶
        </div>
        <div>
          <h2>{t("videoTitle")}</h2>
          <p>{t("videoBody")}</p>
          <Walkthrough />
        </div>
      </section>

      <section className="step">
        <div className="n">1</div>
        <div>
          <h2>{t("step1Title")}</h2>
          <p>{t.rich("step1", tags)}</p>
        </div>
      </section>
      <section className="step">
        <div className="n">2</div>
        <div>
          <h2>{t("step2Title")}</h2>
          <p>{t.rich("step2", tags)}</p>
        </div>
      </section>
      <section className="step">
        <div className="n">3</div>
        <div>
          <h2>{t("step3Title")}</h2>
          <p>{t.rich("step3", tags)}</p>
        </div>
      </section>

      <div className="aside">{t.rich("japan", tags)}</div>
      <div className="aside">{t.rich("already", tags)}</div>
    </Shell>
  );
}
