import type { Metadata } from "next";
import { Shell } from "@/components/Shell";
import { Tutorial } from "@/components/Tutorial";
import { GATEWAY_LOGIN } from "@/lib/gateway";
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
  // the cards are named as the page behind a login link names them
  const flow = await getTranslations("flow");
  const footer = await getTranslations("footer");
  const video = await getTranslations("tutorial");
  const tags = {
    b: (c: React.ReactNode) => <b>{c}</b>,
    em: (c: React.ReactNode) => <em>{c}</em>,
    code: (c: React.ReactNode) => <code>{c}</code>,
    aime: (c: React.ReactNode) => <a href="https://my-aime.net/en/">{c}</a>,
    dash: (c: React.ReactNode) => <a href="/me/">{c}</a>,
    chrome: (c: React.ReactNode) => <a href="/chromeextension">{c}</a>,
    firefox: (c: React.ReactNode) => <a href="/firefoxextension">{c}</a>,
    // the gateway's sign-in is the same address for everyone, so this page can link it without a login link of its own
    gw: (c: React.ReactNode) => <a href={GATEWAY_LOGIN} target="_blank" rel="noopener noreferrer">{c}</a>,
  };
  return (
    <Shell tag="link" lit={1} footLeft={footer("notAffiliated")}>
      <h1>{t.rich("title", tags)}</h1>
      <p className="lede">{t("lede")}</p>

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
          <p>{t("step2")}</p>
          <div className="ways">
            <details className="way first" open>
              <summary>{flow("wayOne")}</summary>
              <div className="way-body">
                <p>{t.rich("oneBody", tags)}</p>
                <Tutorial clip="approve" label={video("approveLabel")} />
              </div>
            </details>
            <details className="way">
              <summary>{flow("wayTwo")}</summary>
              <div className="way-body">
                <p>{t.rich("twoBody", tags)}</p>
                <Tutorial clip="extension" label={video("helperLabel")} />
              </div>
            </details>
            <details className="way">
              <summary>{flow("wayThree")}</summary>
              <div className="way-body">
                <ol className="howto">
                  <li>{t.rich("hand1", tags)}</li>
                  <li>{t.rich("hand2", tags)}</li>
                  <li>{t("hand3")}</li>
                </ol>
                <Tutorial label={video("label")} />
              </div>
            </details>
          </div>
        </div>
      </section>
      <section className="step">
        <div className="n">3</div>
        <div>
          <h2>{t("step3Title")}</h2>
          <p>{t.rich("step3", tags)}</p>
        </div>
      </section>

      <div className="aside">{flow.rich("phones", tags)}</div>
      <div className="aside">{t.rich("japan", tags)}</div>
      <div className="aside">{t.rich("kamaitachi", tags)}</div>
      <div className="aside">{t.rich("already", tags)}</div>
    </Shell>
  );
}
