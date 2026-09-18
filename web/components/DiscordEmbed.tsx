import { serialise, type Embed } from "@/lib/embed";

/**
 * The component-embed tag, server-rendered so Discord's crawler sees it.
 *
 * Nothing is rendered when the payload is over one of Discord's limits: the page's Open Graph tags
 * are the fallback, and they are already there.
 */
export function DiscordEmbed({ embed }: { embed: Embed }) {
  const json = serialise(embed);
  if (!json) return null;
  return <script id="discord:component-embed" type="application/json" dangerouslySetInnerHTML={{ __html: json }} />;
}
