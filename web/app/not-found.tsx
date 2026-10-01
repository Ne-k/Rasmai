import type { Metadata } from "next";
import { Shell } from "@/components/Shell";
import { getI18n } from "@/lib/i18n/server";

export async function generateMetadata(): Promise<Metadata> {
  const { m } = await getI18n();
  return { title: m.notFound.metaTitle, description: m.notFound.metaDescription };
}

export default async function NotFound() {
  const { m } = await getI18n();
  const t = m.notFound;
  return (
    <Shell tag="error" lit={0} footLeft={t.foot}>
      <h1>{t.title}</h1>
      <p className="lede">{t.lede}</p>
      <section className="step">
        <div className="n">→</div>
        <div>
          <h2>{t.whereTitle}</h2>
          <p>{t.home}</p>
          <p>{t.link}</p>
          <p>{t.dashboard}</p>
        </div>
      </section>
      <div className="aside">{t.bookmark}</div>
    </Shell>
  );
}
