import { NextResponse, type NextRequest } from "next/server";

// the link-preview fetchers of chat apps and social sites; search engines are left out, so they index the PDF itself
const PREVIEWERS = /Discordbot|Twitterbot|facebookexternalhit|Facebot|Slackbot|TelegramBot|WhatsApp|LinkedInBot|redditbot|Bluesky|Mastodon|Embedly|Iframely|SkypeUriPreview|vkShare/i;

const TITLE = "Predicting Rating Gains in maimai DX";
const DESCRIPTION = "How Rasmai works out which charts will raise your rating, based on how you play. 19 pages.";

/** A PDF cannot carry an embed, so a previewer asking for the whitepaper gets the tags for one instead. People still get the PDF. */
export function middleware(request: NextRequest) {
  if (!PREVIEWERS.test(request.headers.get("user-agent") ?? "")) return NextResponse.next();
  const site = (process.env.MAIMAI_PUBLIC_URL ?? "https://rasmai.lol").trim().replace(/\/+$/, "");
  const html = `<!doctype html><html lang="en"><head><meta charset="utf-8"><title>${TITLE}</title>
<meta name="description" content="${DESCRIPTION}">
<meta name="theme-color" content="#ff5c9f">
<meta property="og:type" content="article">
<meta property="og:site_name" content="Rasmai">
<meta property="og:title" content="${TITLE}">
<meta property="og:description" content="${DESCRIPTION}">
<meta property="og:url" content="${site}/whitepaper.pdf">
<meta property="og:image" content="${site}/whitepaper/card/">
<meta property="og:image:width" content="1200">
<meta property="og:image:height" content="630">
<meta property="og:image:alt" content="${TITLE}">
<meta name="twitter:card" content="summary_large_image">
</head><body><a href="/whitepaper.pdf">${TITLE}</a></body></html>`;
  // no-store, so no cache between here and the reader can hand this page to a person asking for the PDF
  return new NextResponse(html, {
    headers: { "Content-Type": "text/html; charset=utf-8", "Cache-Control": "no-store", Vary: "User-Agent" },
  });
}

export const config = { matcher: "/whitepaper.pdf" };
