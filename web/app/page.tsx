import type { Metadata } from "next";
import { DiscordEmbed } from "@/components/DiscordEmbed";
import { MastheadNav } from "@/components/Shell";
import { ThemeToggle } from "@/components/Theme";
import { ServersNotice } from "@/components/Servers";
import { Ring } from "@/components/Ring";
import { buttons, embed, headline, rule, say } from "@/lib/embed";
import { env } from "@/lib/env";
import { getI18n } from "@/lib/i18n/server";
import "./landing.css";

const SAMPLE = [
  { tier: "expert", label: "EXPERT 13+", title: "Dragoon", from: "99.12", to: "100.50", ranks: "SS → SSS+", odds: "14%", gain: "+22" },
  { tier: "master", label: "MASTER 13", title: "Starlight Disco", from: "98.60", to: "100.50", ranks: "S+ → SSS+", odds: "11%", gain: "+19" },
  { tier: "expert", label: "EXPERT 12+", title: "Oshama Scramble!", from: "99.71", to: "100.50", ranks: "SS+ → SSS+", odds: "19%", gain: "+11" },
  { tier: "master", label: "MASTER 13+", title: "Imitation:Loud Lounge", from: "97.94", to: "99.00", ranks: "S → SS", odds: "26%", gain: "+9" },
];

export async function generateMetadata(): Promise<Metadata> {
  const { m } = await getI18n();
  return {
    title: m.home.metaTitle,
    description: m.meta.tagline,
    alternates: { canonical: "/" },
    openGraph: { title: `${m.home.metaTitle} · Rasmai`, description: m.meta.tagline, url: "/", images: ["/opengraph-image"] },
  };
}

// what the site is, in the shape search engines read. Only facts that are on the page anyway.
const STRUCTURED = {
  "@context": "https://schema.org",
  "@type": "SoftwareApplication",
  name: "Rasmai",
  applicationCategory: "GameApplication",
  applicationSubCategory: "Discord bot",
  operatingSystem: "Any",
  url: "https://rasmai.lol/",
  description:
    "Rasmai looks at your maimai DX NET scores and tells you which charts to play to raise your rating.",
  isAccessibleForFree: true,
  offers: { "@type": "Offer", price: "0", priceCurrency: "USD" },
  author: { "@type": "Person", name: "nek_ng" },
};

const SITE = env.publicUrl();

// what a link to the front page turns into in Discord, which is where nearly every link to this site
// gets pasted
const UNFURL = embed("#ff3d8f", [
  headline("Rasmai", `${SITE}/`, ["A maimai DX bot for Discord."], { image: `${SITE}/app/icon-512.png` }),
  say(
    "Looks at your maimai DX NET scores and tells you which charts to play to raise your rating.\n\n"
    + "- **What to play**, with the odds for each target\n"
    + "- **A plan** for your next thousand rating\n"
    + "- **Your strong and weak patterns**\n"
    + "- **A web dashboard** with all your scores",
  ),
  rule(),
  buttons(
    { label: "Add to Discord", url: `${SITE}/invite` },
    { label: "Open the dashboard", url: `${SITE}/me/` },
    { label: "Link your account", url: `${SITE}/link/` },
  ),
]);

export default async function LandingPage() {
  const { m } = await getI18n();
  const t = m.home;
  return (
    <>
      <DiscordEmbed embed={UNFURL} />
      <script type="application/ld+json" dangerouslySetInnerHTML={{ __html: JSON.stringify(STRUCTURED) }} />
    <div className="frame landing">
      <header className="masthead">
        <Ring lit={0} size={34} />
        <div className="wordmark">
          Ras<span>mai</span>
        </div>
        <MastheadNav current="home" />
        <ThemeToggle />
      </header>
      <ServersNotice />

      <section className="hero">
        <div className="hero-copy">
          <p className="eyebrow">{t.eyebrow}</p>
          <h1>{t.title}</h1>
          <p className="lede">{t.lede}</p>
          <div className="btn-row">
            <a className="button pink" href="/invite">
              {t.addToDiscord}
            </a>
            <a className="button ghost" href="/me/">
              {t.openDashboard}
            </a>
          </div>
        </div>
        <div className="hero-ring" aria-hidden="true">
          <Ring size={260} chase />
        </div>
      </section>

      <section className="image-demo" aria-label={t.demoLabel}>
        <div className="image">
          <div className="image-head">
            <span className="image-eyebrow">{t.demoEyebrow}</span>
            <span className="image-name">{t.demoName}</span>
            <span className="image-figure">
              <span className="count" aria-label="+61" />
              <small>{t.demoTotal}</small>
            </span>
          </div>
          <table>
            <thead>
              <tr>
                <th>#</th>
                <th>{t.columns.chart}</th>
                <th>{t.columns.achievement}</th>
                <th>{t.columns.rank}</th>
                <th>{t.columns.odds}</th>
                <th>{t.columns.gain}</th>
              </tr>
            </thead>
            <tbody>
              {SAMPLE.map((row, i) => (
                <tr key={row.title} style={{ "--i": i } as React.CSSProperties}>
                  <td className="n">{i + 1}</td>
                  <td>
                    <span className="t">{row.title}</span>
                    <span className={`tier ${row.tier}`}>{row.label}</span>
                  </td>
                  <td className="num">
                    {row.from} → <b>{row.to}</b>
                  </td>
                  <td className="num">{row.ranks}</td>
                  <td className="num">{row.odds}</td>
                  <td className="num gain">{row.gain}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <div className="image-foot">
            <span>rasmai · maimai DX</span>
            <span>{t.demoFoot}</span>
          </div>
        </div>
      </section>

      <section className="features">
        {t.features.map((f) => (
          <article key={f.title} className="feature">
            <img src={`/marks/${f.mark}.svg`} alt="" width={44} height={44} />
            <h2>{f.title}</h2>
            <p>{f.body}</p>
            <code>{f.command}</code>
          </article>
        ))}
      </section>

      <section className="split">
        <div>
          <h2 className="section-title">{t.linkingTitle}</h2>
          <p>{t.linking}</p>
          <a className="button" href="/link/">
            {t.linkingButton}
          </a>
        </div>
        <div>
          <h2 className="section-title">{t.dashboardTitle}</h2>
          <p>{t.dashboard}</p>
          <a className="button ghost" href="/me/">
            {t.dashboardButton}
          </a>
          <p className="hint" style={{ marginTop: 14 }}>
            {t.phoneHint}
          </p>
        </div>
      </section>

      <section className="commands">
        <h2 className="section-title">{t.commandsTitle}</h2>
        <ul className="cmds">
          {t.commands.map(([cmd, what]) => (
            <li key={cmd}>
              <code>{cmd}</code>
              <span>{what}</span>
            </li>
          ))}
        </ul>
      </section>

      <footer className="foot">
        <span>
          {m.footer.createdBy} · {m.footer.notAffiliated} · <a href="/privacy/">{m.footer.privacy}</a> ·{" "}
          <a href="/terms/">{m.footer.terms}</a>
        </span>
        {/* <span>
          <a href="https://github.com/Ne-k/razmai">source on GitHub</a>
        </span> */}
      </footer>
    </div>
    </>
  );
}
