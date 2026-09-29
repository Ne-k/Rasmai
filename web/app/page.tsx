import type { Metadata } from "next";
import { DiscordEmbed } from "@/components/DiscordEmbed";
import { MastheadNav } from "@/components/Shell";
import { ThemeToggle } from "@/components/Theme";
import { ServersNotice } from "@/components/Servers";
import { Ring } from "@/components/Ring";
import { buttons, embed, headline, rule, say } from "@/lib/embed";
import { env } from "@/lib/env";
import "./landing.css";

const FEATURES: { mark: string; title: string; body: string; command: string }[] = [
  {
    mark: "rank_sssp",
    title: "What to grind for rating",
    body: "Goes through your scores and lists the charts where a better score would raise your rating the most.",
    command: "/analyze",
  },
  {
    mark: "up",
    title: "Pick how hard you want it",
    body: "Easier gives safer targets and Balanced gives the best expected gain. Challenging goes for bigger gains that are still doable. You can switch it from a dropdown on the reply.",
    command: "/analyze challenge",
  },
  {
    mark: "best50",
    title: "Plan your next thousand",
    body: "A list of targets that add up to your next rating milestone, with the odds for each and a running total.",
    command: "/plan",
  },
  {
    mark: "plays",
    title: "Plan a session",
    body: "Tell it how many credits you have and it plans each one, warm-ups first. A chart only repeats if you missed it the first time, and you can see how much rating the session could get you.",
    command: "/session",
  },
  {
    mark: "new",
    title: "New charts to try",
    body: "Charts you haven't played yet that fit your level, with a guess at what you'd score first try. Add a focus to lean toward patterns you're weak or strong at.",
    command: "/new focus",
  },
  {
    mark: "pb",
    title: "Where you lose points",
    body: "Your scores grouped by chart pattern and compared to your own curve. It also shows how well the predictions have matched your new bests.",
    command: "/profile",
  },
  {
    mark: "diff_master",
    title: "Look up a chart",
    body: "Shows your score, the predicted score, what each rank is worth and the chart's patterns. The song's other difficulties and a score history graph are a button away. You can also browse every chart with a given pattern.",
    command: "/chart  /charts",
  },
  {
    mark: "rasmai",
    title: "Track your rating",
    body: "Your rating over time, how fast it's going up, when you'd hit each milestone at that pace, and how many credits the route would take.",
    command: "/progress",
  },
  {
    mark: "festival",
    title: "Check your plays",
    body: "Pattern tags show what's in a chart before you play it. After a play, the play log shows every judgement so you can see where you lost points.",
    command: "/charts  /recent play:1",
  },
];

const COMMANDS: [string, string][] = [
  ["/login", "link your maimai DX NET account"],
  ["/analyze", "what to grind, at the difficulty you pick"],
  ["/plan", "a route to your next rating milestone"],
  ["/session", "plan your credits for a session"],
  ["/new", "unplayed charts at your level, with an option to focus on weak spots"],
  ["/chart  /charts", "look up one chart, or list charts by pattern or level"],
  ["/b50  /dxscore", "your best 50 (also /top) and DX score stars"],
  ["/recent", "your recent plays, or one play in detail with play:1"],
  ["/progress", "your rating over time and when you'll hit the next thousand"],
  ["/compare  /leaderboard", "you vs a friend, or a server leaderboard (opt-in)"],
  ["/random  /profile  /export", "a random chart, how you play, a copy of your data"],
  ["/settings  /invite", "your defaults and daily score check, and the invite link"],
];

const SAMPLE = [
  { tier: "expert", label: "EXPERT 13+", title: "Dragoon", from: "99.12", to: "100.50", ranks: "SS → SSS+", odds: "14%", gain: "+22" },
  { tier: "master", label: "MASTER 13", title: "Starlight Disco", from: "98.60", to: "100.50", ranks: "S+ → SSS+", odds: "11%", gain: "+19" },
  { tier: "expert", label: "EXPERT 12+", title: "Oshama Scramble!", from: "99.71", to: "100.50", ranks: "SS+ → SSS+", odds: "19%", gain: "+11" },
  { tier: "master", label: "MASTER 13+", title: "Imitation:Loud Lounge", from: "97.94", to: "99.00", ranks: "S → SS", odds: "26%", gain: "+9" },
];

export const metadata: Metadata = {
  title: "maimai DX rating bot for Discord",
  description: "Rasmai looks at your maimai DX NET scores and tells you which charts to play to raise your rating.",
  alternates: { canonical: "/" },
  openGraph: { title: "maimai DX rating bot for Discord · Rasmai", description: "Rasmai looks at your maimai DX NET scores and tells you which charts to play to raise your rating.", url: "/" , images: ["/opengraph-image"] },
};

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

export default function LandingPage() {
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
          <p className="eyebrow">A Discord bot for maimai DX</p>
          <h1>
            See which charts to <em>play next</em>.
          </h1>
          <p className="lede">
            Rasmai looks at your maimai DX NET scores and tells you which charts to play to raise your rating. You get the
            results as images in Discord or on the web dashboard, and you can look up any chart&apos;s patterns before you play it.
          </p>
          <div className="btn-row">
            <a className="button pink" href="/invite">
              add to Discord
            </a>
            <a className="button ghost" href="/me/">
              open your dashboard
            </a>
          </div>
        </div>
        <div className="hero-ring" aria-hidden="true">
          <Ring size={260} chase />
        </div>
      </section>

      <section className="image-demo" aria-label="What a result looks like">
        <div className="image">
          <div className="image-head">
            <span className="image-eyebrow">what to play next</span>
            <span className="image-name">your name here</span>
            <span className="image-figure">
              <span className="count" aria-label="+61" />
              <small>total gain</small>
            </span>
          </div>
          <table>
            <thead>
              <tr>
                <th>#</th>
                <th>Chart</th>
                <th>Achievement</th>
                <th>Rank</th>
                <th>Odds</th>
                <th>Gain</th>
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
            <span>example · yours uses your scores</span>
          </div>
        </div>
      </section>

      <section className="features">
        {FEATURES.map((f) => (
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
          <h2 className="section-title">Linking your account</h2>
          <p>
            Run <code>/login</code> in Discord and follow the link. You sign in at my-aime.net, open the Aime authentication, then press a
            bookmark once. Rasmai only gets the session it needs to read your scores and never sees your password.{" "}
            <code>/delete-account</code> deletes everything it has on you.
          </p>
          <a className="button" href="/link/">
            how linking works →
          </a>
        </div>
        <div>
          <h2 className="section-title">The dashboard</h2>
          <p>
            Sign in with Discord to see your rating over time, how you play, your best 50, all your scores with filters, the same
            picks as the bot, and 40 unplayed charts to try.
          </p>
          <a className="button ghost" href="/me/">
            open the dashboard →
          </a>
          <p className="hint" style={{ marginTop: 14 }}>
            On a phone, add the dashboard to your home screen and it opens like an app.
          </p>
        </div>
      </section>

      <section className="commands">
        <h2 className="section-title">Commands</h2>
        <ul className="cmds">
          {COMMANDS.map(([cmd, what]) => (
            <li key={cmd}>
              <code>{cmd}</code>
              <span>{what}</span>
            </li>
          ))}
        </ul>
      </section>

      <footer className="foot">
        <span>
          Created by <b>nek_ng</b> · not affiliated with SEGA · <a href="/privacy/">privacy</a> ·{" "}
          <a href="/terms/">terms</a>
        </span>
        {/* <span>
          <a href="https://github.com/Ne-k/razmai">source on GitHub</a>
        </span> */}
      </footer>
    </div>
    </>
  );
}
