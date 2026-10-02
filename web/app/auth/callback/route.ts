import { authorizeUrl, exchangeCode } from "@/lib/discord";
import { clientKey, redirect } from "@/lib/http";
import { oauthLimiter } from "@/lib/limiter";
import { back, finishSignIn, newFlow, readFlow, withFlow } from "@/lib/signin";

// Discord's answers when it wants the person to see the consent screen that prompt=none skipped
const NEEDS_CONSENT = ["interaction_required", "consent_required", "login_required"];

export async function GET(request: Request) {
  if (!oauthLimiter.allow(clientKey(request))) return redirect("/me/?error=rate_limited");
  const url = new URL(request.url);
  const flow = readFlow(request, "discord", url.searchParams.get("state") ?? "");
  if (!flow) return back("state");

  const refused = url.searchParams.get("error") ?? "";
  if (refused) {
    if (!NEEDS_CONSENT.includes(refused) || flow.retried) return back("discord");
    // someone who signed in before the email scope existed has not agreed to it yet: ask once more, with the screen
    const again = newFlow("discord", flow.link, flow.keep, true);
    return withFlow(redirect(authorizeUrl(again.state, false)), again);
  }
  const code = url.searchParams.get("code") ?? "";
  if (!code) return back("state");

  let identity;
  try {
    identity = await exchangeCode(code);
  } catch (error) {
    console.warn("Discord sign-in failed:", error);
    return back("discord");
  }
  return finishSignIn(request, flow, identity);
}
