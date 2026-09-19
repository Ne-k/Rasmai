// What a link to this site turns into when somebody pastes it in Discord. A component embed replaces
// the ordinary title-description-picture card with a layout we choose, buttons included.
// https://discord.com/developers/docs/link-previews/component-embeds
//
// Discord does not run JavaScript, so this has to be in the HTML the server sends; a tag added in the
// browser is never seen. The Open Graph tags stay exactly where they are. They are what Discord falls
// back to whenever this payload cannot be used, and they are what every other site that unfurls a
// link reads instead.

// the only button style a component embed may carry, and the only keys a button may have
const LINK = 5;

// Discord reads this many bytes of JSON and renders this many components. Going over either is not
// an error it reports: the embed simply does not appear, so both are checked here instead.
const LIMIT = 3000;
const PIECES = 40;

export type Media = { url: string; description?: string };

type Text = { type: 10; content: string };
type Thumbnail = { type: 11; media: { url: string } };
type Button = { type: 2; style: typeof LINK; label: string; url: string };
type Row = { type: 1; components: Button[] };
// a section's accessory is not optional. Leave it out and Discord refuses the whole payload with
// BASE_TYPE_REQUIRED and shows nothing at all, so the type demands one rather than trusting a caller
// to remember.
type Section = { type: 9; components: Text[]; accessory: Thumbnail | Button };
type Gallery = { type: 12; items: { media: { url: string }; description?: string }[] };
type Rule = { type: 14; spacing?: 1 | 2 };
export type Piece = Text | Section | Gallery | Rule | Row;
export type Embed = { type: 17; accent_color?: number; components: Piece[] };

/** Text as itself, not as markup: a title with a `*` or a `#` in it is a title, not a heading. */
export function plain(text: string): string {
  return String(text ?? "").replace(/([\\*_~`|#>[\]])/g, "\\$1");
}

/** A link target markdown will not cut short on its own brackets. */
function href(url: string): string {
  return String(url ?? "").replace(/\(/g, "%28").replace(/\)/g, "%29");
}

/** One paragraph of Discord markdown. */
export function say(content: string): Text {
  return { type: 10, content };
}

/**
 * The headline: a linked title, whatever lines follow it, and a picture or a button off to the side.
 *
 * The thing off to the side is required, so it is an argument rather than an option.
 */
export function headline(
  title: string,
  url: string,
  lines: string[],
  aside: { image: string } | { label: string; url: string },
): Section {
  const heading = `## **[${plain(title)}](${href(url)})**`;
  const accessory: Thumbnail | Button = "image" in aside
    ? { type: 11, media: { url: aside.image } }
    : { type: 2, style: LINK, label: plain(aside.label), url: aside.url };
  return { type: 9, components: [say([heading, ...lines].join("\n"))], accessory };
}

/** A row of link buttons. Discord fits five to a row. */
export function buttons(...items: { label: string; url: string }[]): Row {
  return {
    type: 1,
    components: items.slice(0, 5).map((item) => ({ type: 2, style: LINK, label: plain(item.label), url: item.url })),
  };
}

/** A dividing line. */
export function rule(spacing: 1 | 2 = 1): Rule {
  return { type: 14, spacing };
}

/** Pictures in a strip, up to ten. */
export function gallery(items: Media[]): Gallery {
  return {
    type: 12,
    items: items.slice(0, 10).map((item) => ({
      media: { url: item.url },
      ...(item.description ? { description: item.description } : {}),
    })),
  };
}

/** The whole embed: one container holding everything, in the site's own colour. */
export function embed(accent: string, pieces: (Piece | null | undefined)[]): Embed {
  const hex = accent.replace(/^#/, "");
  const container: Embed = { type: 17, components: pieces.filter(Boolean) as Piece[] };
  if (/^[0-9a-f]{6}$/i.test(hex)) container.accent_color = parseInt(hex, 16);
  return container;
}

/** How many components this is, counting the container and everything inside it. */
function count(pieces: Piece[]): number {
  let total = 0;
  for (const piece of pieces) {
    total += 1;
    if (piece.type === 9) total += piece.components.length + (piece.accessory ? 1 : 0);
    else if (piece.type === 1) total += piece.components.length;
  }
  return total;
}

/**
 * The payload as it goes in the page, or `null` when it would be refused.
 *
 * `<` is written as an escape so the JSON cannot close the script tag it sits in, whatever ends up
 * inside it. An embed over either of Discord's limits is dropped rather than served, because a
 * payload Discord refuses is worse than none: the Open Graph card still works.
 */
export function serialise(container: Embed): string | null {
  const pieces = count(container.components) + 1;
  if (pieces > PIECES) {
    console.warn(`discord embed: ${pieces} components, over the ${PIECES} Discord renders`);
    return null;
  }
  const json = JSON.stringify({ component: container }).replace(/</g, "\\u003c");
  const bytes = Buffer.byteLength(json, "utf8");
  if (bytes > LIMIT) {
    console.warn(`discord embed: ${bytes} bytes, over the ${LIMIT} Discord reads`);
    return null;
  }
  return json;
}
