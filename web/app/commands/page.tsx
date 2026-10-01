import type { Metadata } from "next";
import { DiscordEmbed } from "@/components/DiscordEmbed";
import { Doc } from "@/components/Doc";
import { getI18n } from "@/lib/i18n/server";
import { buttons, embed, headline, rule, say } from "@/lib/embed";
import { env } from "@/lib/env";

export async function generateMetadata(): Promise<Metadata> {
  const { m } = await getI18n();
  return {
    title: m.commands.metaTitle,
    description: m.commands.metaDescription,
    alternates: { canonical: "/commands/" },
    openGraph: { title: `${m.commands.metaTitle} · Rasmai`, description: m.commands.metaDescription, url: "/commands/", images: ["/opengraph-image"] },
  };
}

const SITE = env.publicUrl();

// the card this page unfurls into. Every command on it, grouped, so somebody who is sent the link
// gets the answer in the channel and only opens the page if they want the detail. Cyan rather than
// the front page's pink, so the two are told apart at a glance.
const UNFURL = embed("#21c3e3", [
  headline("Rasmai commands", `${SITE}/commands/`, ["All the commands and what they do."],
    { image: `${SITE}/app/icon-512.png` }),
  say(
    "**Play**\n`/analyze` `/plan` `/session` `/new` `/random`\n\n"
    + "**Scores**\n`/b50` `/chart` `/charts` `/recent` `/dxscore` `/progress` `/area`\n\n"
    + "**You**\n`/profile` `/compare` `/leaderboard`\n\n"
    + "**Account**\n`/login` `/settings` `/refresh` `/export` `/delete-account`",
  ),
  rule(),
  say("-# Hover any maimai word on the page for what it means."),
  buttons(
    { label: "Read the page", url: `${SITE}/commands/` },
    { label: "Add to Discord", url: `${SITE}/invite` },
  ),
]);

export default async function CommandsPage() {
  const { m } = await getI18n();
  return (
    <>
      <DiscordEmbed embed={UNFURL} />
      <Doc
      tag="commands"
      dated={false}
      title={m.commands.title}
      intro={m.commands.intro}
    >
      {m.docs.commands()}
      </Doc>
    </>
  );
}
