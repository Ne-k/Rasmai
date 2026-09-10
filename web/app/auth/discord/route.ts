import { randomBytes } from "node:crypto";
import { authorizeUrl } from "@/lib/discord";
import { oauthReady, turnstileReady } from "@/lib/env";
import { clientKey, parseBody, redirect, sameOrigin } from "@/lib/http";
import { STATE_COOKIE, STATE_TTL, cookieHeader, sign } from "@/lib/session";
import { verifyTurnstile } from "@/lib/turnstile";

export const dynamic = "force-dynamic";

/** Remember a state nonce in a signed cookie and send the browser to Discord. */
function start() {
  const state = randomBytes(24).toString("base64url");
  const response = redirect(authorizeUrl(state));
  response.headers.append("Set-Cookie", cookieHeader(STATE_COOKIE, sign({ state, exp: Date.now() / 1000 + STATE_TTL }), STATE_TTL));
  return response;
}

export async function GET() {
  if (!oauthReady()) return redirect("/me/?error=oauth_unconfigured");
  if (turnstileReady()) return redirect("/me/"); // the sign-in is a form post carrying the widget's token
  return start();
}

export async function POST(request: Request) {
  if (!sameOrigin(request)) return redirect("/me/?error=state");
  if (!oauthReady()) return redirect("/me/?error=oauth_unconfigured");
  let body: Record<string, string> = {};
  try {
    body = await parseBody(request);
  } catch {
    body = {};
  }
  const verdict = await verifyTurnstile(body["cf-turnstile-response"] ?? "", clientKey(request), "dashboard");
  if (!verdict.ok) {
    console.info("turnstile rejected a dashboard sign-in:", verdict.codes.join(","));
    return redirect("/me/?error=verify");
  }
  return start();
}
