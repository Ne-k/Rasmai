import { clientKey, redirect } from "@/lib/http";
import { internal } from "@/lib/internal";
import { oauthLimiter } from "@/lib/limiter";
import { currentUser } from "@/lib/session";

const AUTHORIZE = "https://kamai.tachi.ac/oauth/request-auth?";

export async function GET(request: Request) {
  const client = clientKey(request);
  if (!oauthLimiter.allow(client)) return redirect("/me/?error=rate_limited");
  const user = currentUser(request);
  if (!user) return redirect("/me/?error=signed_out");
  let error = "kamaitachi";
  try {
    const upstream = await internal("/internal/me/kamaitachi/connect", { method: "POST", user, client });
    const answer = (await upstream.json().catch(() => ({}))) as Record<string, unknown>;
    // the bot's answer decides where the browser goes, so only Kamaitachi's own approval page is followed
    if (upstream.ok && typeof answer.url === "string" && answer.url.startsWith(AUTHORIZE)) return redirect(answer.url);
    if (answer.error === "kamaitachi_unconfigured" || answer.error === "rate_limited") error = answer.error;
  } catch {
    // the bot is unreachable: the generic Kamaitachi message covers it
  }
  console.warn("Kamaitachi connect failed:", error);
  return redirect(`/me/?error=${error}`);
}
