import type { Metadata } from "next";
import { Shell } from "@/components/Shell";
import { Walkthrough } from "@/components/Walkthrough";

export const metadata: Metadata = {
  title: "Link your maimai account",
  description: "How to link your maimai DX NET account to Rasmai on a computer or iPhone, with a video.",
  alternates: { canonical: "/link/" },
  openGraph: { title: "Link your maimai account · Rasmai", description: "How to link your maimai DX NET account to Rasmai on a computer or iPhone, with a video.", url: "/link/" , images: ["/opengraph-image"] },
};

export default function LinkPage() {
  return (
    <Shell tag="link" lit={1} footLeft="not affiliated with SEGA">
      <h1>
        Link your <em>maimai</em> account.
      </h1>
      <p className="lede">
        Once you&apos;re linked, Rasmai checks your scores and tells you which charts to play to raise your rating.
      </p>

      <section className="step walk-step">
        <div className="n" aria-hidden="true">
          ▶
        </div>
        <div>
          <h2>Watch the video first</h2>
          <p>Pick your device. It&apos;s about a minute long with no sound.</p>
          <Walkthrough />
        </div>
      </section>

      <section className="step">
        <div className="n">1</div>
        <div>
          <h2>Get your link</h2>
          <p>
            Run <code>/login</code> in Discord. You&apos;ll get a private link to this site with your login code already
            filled in.
          </p>
        </div>
      </section>
      <section className="step">
        <div className="n">2</div>
        <div>
          <h2>Sign in at my-aime, then authenticate</h2>
          <p>
            Sign in at <a href="https://my-aime.net/en/">my-aime.net</a> with the account you play on, then open the Aime authentication
            from the setup page. That takes you to the gateway page.
          </p>
        </div>
      </section>
      <section className="step">
        <div className="n">3</div>
        <div>
          <h2>Start grinding</h2>
          <p>
            Back in Discord, run <code>/analyze</code> to see what to play or <code>/plan</code> to plan your next thousand.
          </p>
        </div>
      </section>

      <div className="aside">
        <b>Already linked?</b> Your scores are on the web too. <a href="/me/">Open your dashboard</a> and sign in with
        Discord.
      </div>
    </Shell>
  );
}
