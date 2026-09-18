import type { Metadata } from "next";
import { DiscordEmbed } from "@/components/DiscordEmbed";
import { PublicProfile } from "@/components/PublicProfile";
import { buttons, embed, headline, type Embed } from "@/lib/embed";
import { env } from "@/lib/env";
import { internal } from "@/lib/internal";
import "../../me/dashboard.css";

// a shared link is for the people it was sent to, not for search engines
export const metadata: Metadata = { title: "A maimai profile · Rasmai", robots: { index: false, follow: false } };

// one visitor's profile is never another's, so nothing here is held
export const dynamic = "force-dynamic";

const SLUG = /^[A-Za-z0-9_-]{16,64}$/;
const SITE = env.publicUrl();

type Shared = { name?: string; rating?: number; region?: string; charts?: number };

/**
 * The card a shared profile unfurls into when its link is pasted in Discord.
 *
 * Only what the page's own header shows to anyone holding the link: the name, the rating, the region
 * and how many charts are behind it. The sections a player opted into, their best 50 and their recent
 * plays, stay on the page. Opening a link is a choice; a card in a channel is seen by everyone there.
 *
 * A profile that is switched off answers as if it never existed, so it gets no card either.
 */
async function unfurl(slug: string): Promise<Embed | null> {
  if (!SLUG.test(slug)) return null;
  let shared: Shared;
  try {
    const answer = await internal(`/internal/public/${slug}`);
    if (!answer.ok) return null;
    shared = (await answer.json()) as Shared;
  } catch {
    // the bot is unreachable: the page's Open Graph card still works
    return null;
  }
  const name = String(shared.name || "").trim();
  const rating = Number(shared.rating || 0);
  if (!name || !rating) return null;

  const region = String(shared.region || "").toUpperCase() === "JP" ? "Japan" : "international";
  const charts = Number(shared.charts || 0);
  const scored = charts ? ` · ${charts.toLocaleString("en")} charts scored` : "";
  return embed("#ff3d8f", [
    headline(name, `${SITE}/p/${slug}`, [`**${rating.toLocaleString("en")}** rating · ${region}${scored}`],
      `${SITE}/app/icon-512.png`),
    buttons(
      { label: "See the profile", url: `${SITE}/p/${slug}` },
      { label: "Get your own", url: `${SITE}/invite` },
    ),
  ]);
}

export default async function SharedProfilePage({ params }: { params: Promise<{ slug: string }> }) {
  const { slug } = await params;
  const card = await unfurl(slug);
  return (
    <>
      {card ? <DiscordEmbed embed={card} /> : null}
      <PublicProfile slug={slug} />
    </>
  );
}
