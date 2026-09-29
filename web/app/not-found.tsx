import type { Metadata } from "next";
import { Shell } from "@/components/Shell";

export const metadata: Metadata = {
  title: "Rasmai · not found",
  description: "This page doesn't exist.",
};

export default function NotFound() {
  return (
    <Shell tag="error" lit={0} footLeft="404 · nothing was saved">
      <h1>
        Page not <em>found</em>.
      </h1>
      <p className="lede">This page doesn&apos;t exist or it moved. Here are some pages that do.</p>
      <section className="step">
        <div className="n">→</div>
        <div>
          <h2>Where to go</h2>
          <p>
            <a href="/">Home</a> to see what Rasmai does and how to add it.
          </p>
          <p>
            <a href="/link/">Link your account</a> if you came here from <code>/login</code>. If your link expired, run the
            command again in Discord for a new one.
          </p>
          <p>
            <a href="/me/">Your dashboard</a>, after signing in with Discord.
          </p>
        </div>
      </section>
      <div className="aside">
        <b>Came from the bookmark?</b> Connect links work once and last about ten minutes. Run the bookmark on the SEGA
        gateway page, not on this site.
      </div>
    </Shell>
  );
}
