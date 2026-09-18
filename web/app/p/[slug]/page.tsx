import type { Metadata } from "next";
import { headers } from "next/headers";
import { cache } from "react";
import { DiscordEmbed } from "@/components/DiscordEmbed";
import { PublicProfile } from "@/components/PublicProfile";
import { buttons, embed, gallery, headline, type Embed } from "@/lib/embed";
import { env } from "@/lib/env";
import { internal } from "@/lib/internal";
import "../../me/dashboard.css";

// one visitor's profile is never another's, so nothing here is held
export const dynamic = "force-dynamic";

const SLUG = /^[A-Za-z0-9_-]{10,64}$/;
const SITE = env.publicUrl();

type Shared = { name?: string; rating?: number; region?: string; charts?: number };

/**
 * The profile as anyone holding the link may read it, or nothing when the link is not in use.
 *
 * Cached for the render, because the page and the card above it both want it and the bot counts
 * every read against whoever asked. The visitor's address goes with the call for the same reason:
 * without it every reader of every profile shares one allowance, which is one shut door away from
 * no link preview at all.
 */
const shared = cache(async (slug: string): Promise<Shared | null> => {
  if (!SLUG.test(slug)) return null;
  try {
    const client = (await headers()).get("cf-connecting-ip") ?? (await headers()).get("x-forwarded-for") ?? "";
    const answer = await internal(`/internal/public/${slug}`, { client: client.split(",")[0].trim() || "local" });
    if (!answer.ok) return null;
    const payload = (await answer.json()) as Shared;
    return String(payload.name || "").trim() ? payload : null;
  } catch {
    // the bot is unreachable: the page's own card still stands
    return null;
  }
});

// a shared link is for the people it was sent to, not for search engines. The picture is the one
// Discord shows above the link, so the two agree wherever a component embed cannot be used.
export async function generateMetadata({ params }: { params: Promise<{ slug: string }> }): Promise<Metadata> {
  const { slug } = await params;
  const profile = await shared(slug);
  const name = String(profile?.name || "").trim();
  return {
    title: name ? `${name} · a maimai profile` : "A maimai profile · Rasmai",
    description: name ? `${name}'s maimai DX rating and charts, shared with Rasmai.` : undefined,
    robots: { index: false, follow: false },
    openGraph: name
      ? { title: `${name} · a maimai profile`, images: [{ url: `${SITE}/p/${slug}/card.png`, width: 1200, height: 630 }] }
      : undefined,
    twitter: name ? { card: "summary_large_image" } : undefined,
  };
}

/**
 * The card a shared profile unfurls into when its link is pasted in Discord.
 *
 * Only what the page's own header shows to anyone holding the link: the picture, the name, the
 * rating, the region and how many charts are behind it. The sections a player opted into, their
 * best 50 and their recent plays, stay on the page. Opening a link is a choice; a card in a channel
 * is seen by everyone there.
 *
 * A profile that is switched off answers as if it never existed, so it gets no card either.
 */
function unfurl(slug: string, profile: Shared): Embed | null {
  const name = String(profile.name || "").trim();
  const rating = Number(profile.rating || 0);
  if (!name || !rating) return null;

  const region = String(profile.region || "").toUpperCase() === "JP" ? "Japan" : "international";
  const charts = Number(profile.charts || 0);
  const scored = charts ? ` · ${charts.toLocaleString("en")} charts scored` : "";
  const here = `${SITE}/p/${slug}`;
  return embed("#ff3d8f", [
    gallery([{ url: `${here}/card.png`, description: `${name}, ${rating.toLocaleString("en")} rating` }]),
    headline(name, here, [`**${rating.toLocaleString("en")}** rating · ${region}${scored}`]),
    buttons(
      { label: "See the profile", url: here },
      { label: "What Rasmai is", url: `${SITE}/` },
    ),
  ]);
}

export default async function SharedProfilePage({ params }: { params: Promise<{ slug: string }> }) {
  const { slug } = await params;
  const profile = await shared(slug);
  const card = profile ? unfurl(slug, profile) : null;
  return (
    <>
      {card ? <DiscordEmbed embed={card} /> : null}
      <PublicProfile slug={slug} />
    </>
  );
}
