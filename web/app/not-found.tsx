import type { Metadata } from "next";
import { Shell } from "@/components/Shell";

export const metadata: Metadata = {
  title: "Rasmai · not found",
  description: "There is no page at this address.",
};

export default function NotFound() {
  return (
    <Shell tag="error" lit={0} footLeft="404 · nothing was saved">
      <h1>
        No chart at this <em>address</em>.
      </h1>
      <p className="lede">
        The page you asked for does not exist, or it moved. Nothing about your account changed. The pages that do exist are
        below.
      </p>
      <section className="step">
        <div className="n">→</div>
        <div>
          <h2>Where to go</h2>
          <p>
            <a href="/">Home</a>, what the bot does and how to add it.
          </p>
          <p>
            <a href="/link/">Link your account</a>, if you came here from <code>/login</code>. Run the command again in
            Discord for a fresh link if yours expired.
          </p>
          <p>
            <a href="/me/">Your dashboard</a>, signed in with Discord.
          </p>
        </div>
      </section>
      <div className="aside">
        <b>Came from a bookmark?</b> Connect links work once and last about ten minutes; the bookmark itself lives on
        the SEGA gateway page, not here.
      </div>
    </Shell>
  );
}
