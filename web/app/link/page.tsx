import type { Metadata } from "next";
import { Shell } from "@/components/Shell";
import { Walkthrough } from "@/components/Walkthrough";
import { getI18n } from "@/lib/i18n/server";

export async function generateMetadata(): Promise<Metadata> {
  const { m } = await getI18n();
  return {
    title: m.link.metaTitle,
    description: m.link.metaDescription,
    alternates: { canonical: "/link/" },
    openGraph: { title: `${m.link.metaTitle} · Rasmai`, description: m.link.metaDescription, url: "/link/", images: ["/opengraph-image"] },
  };
}

export default async function LinkPage() {
  const { m } = await getI18n();
  const t = m.link;
  return (
    <Shell tag="link" lit={1} footLeft={m.footer.notAffiliated}>
      <h1>{t.title}</h1>
      <p className="lede">{t.lede}</p>

      <section className="step walk-step">
        <div className="n" aria-hidden="true">
          ▶
        </div>
        <div>
          <h2>{t.videoTitle}</h2>
          <p>{t.videoBody}</p>
          <Walkthrough />
        </div>
      </section>

      <section className="step">
        <div className="n">1</div>
        <div>
          <h2>{t.step1Title}</h2>
          <p>{t.step1}</p>
        </div>
      </section>
      <section className="step">
        <div className="n">2</div>
        <div>
          <h2>{t.step2Title}</h2>
          <p>{t.step2}</p>
        </div>
      </section>
      <section className="step">
        <div className="n">3</div>
        <div>
          <h2>{t.step3Title}</h2>
          <p>{t.step3}</p>
        </div>
      </section>

      <div className="aside">{t.japan}</div>
      <div className="aside">{t.already}</div>
    </Shell>
  );
}
