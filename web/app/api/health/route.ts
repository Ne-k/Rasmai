import { json } from "@/lib/http";
import { internal } from "@/lib/internal";

export const dynamic = "force-dynamic";

/** The site is up; `bot` says whether the bot's internal API answers too. */
export async function GET() {
  let bot = false;
  try {
    bot = (await internal("/health")).ok;
  } catch {
    bot = false;
  }
  return json(200, { ok: true, bot, time: new Date().toISOString() });
}
