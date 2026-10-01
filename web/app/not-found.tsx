import type { Metadata } from "next";
import { Shell } from "@/components/Shell";
import { Support } from "@/components/Support";
import { getTranslations } from "next-intl/server";

export async function generateMetadata(): Promise<Metadata> {
  const t = await getTranslations("notFound");
  return { title: t("metaTitle"), description: t("metaDescription") };
}

export default async function NotFound() {
  const t = await getTranslations("notFound");
  const tags = {
    b: (c: React.ReactNode) => <b>{c}</b>,
    em: (c: React.ReactNode) => <em>{c}</em>,
    code: (c: React.ReactNode) => <code>{c}</code>,
    home: (c: React.ReactNode) => <a href="/">{c}</a>,
    link: (c: React.ReactNode) => <a href="/link/">{c}</a>,
    dash: (c: React.ReactNode) => <a href="/me/">{c}</a>,
  };
  return (
    <Shell tag="error" lit={0} footLeft={t("foot")}>
      <h1>{t.rich("title", tags)}</h1>
      <p className="lede">{t("lede")}</p>
      <section className="step">
        <div className="n">→</div>
        <div>
          <h2>{t("whereTitle")}</h2>
          <p>{t.rich("home", tags)}</p>
          <p>{t.rich("link", tags)}</p>
          <p>{t.rich("dashboard", tags)}</p>
        </div>
      </section>
      <div className="aside">{t.rich("bookmark", tags)}</div>
      <Support />
    </Shell>
  );
}
