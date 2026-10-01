import type { Metadata } from "next";
import { DiscordEmbed } from "@/components/DiscordEmbed";
import { Doc } from "@/components/Doc";
import { docBody } from "@/components/DocBody";
import { getTranslations } from "next-intl/server";
import { buttons, embed, headline, rule, say } from "@/lib/embed";
import { env } from "@/lib/env";

export async function generateMetadata(): Promise<Metadata> {
  const t = await getTranslations("commands");
  return {
    title: t("metaTitle"),
    description: t("metaDescription"),
    alternates: { canonical: "/commands/" },
    openGraph: { title: `${t("metaTitle")} · Rasmai`, description: t("metaDescription"), url: "/commands/", images: ["/opengraph-image"] },
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
  const t = await getTranslations("commands");
  return (
    <>
      <DiscordEmbed embed={UNFURL} />
      <Doc
      tag="commands"
      dated={false}
      title={t.rich("title", { em: (c) => <em>{c}</em> })}
      intro={t("intro")}
    >
      {await docBody("commands")}
      </Doc>
    </>
  );
}
