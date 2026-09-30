import { NextResponse } from "next/server";
import { env } from "@/lib/env";
import { internal } from "@/lib/internal";

/** The site is up; `bot` says whether the bot's internal API answers too, and `statusUrl` is where the status page lives, when there is one.
 *
 * Every page's masthead asks this, so the answer is good for a few seconds rather than fetched from the bot each time. */
export async function GET() {
  let bot = false;
  try {
    bot = (await internal("/health")).ok;
  } catch {
    bot = false;
  }
  return NextResponse.json(
    { ok: true, bot, statusUrl: env.statusUrl(), time: new Date().toISOString() },
    { headers: { "Cache-Control": "public, max-age=15, s-maxage=30" } },
  );
}
