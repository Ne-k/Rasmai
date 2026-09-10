import { env, oauthReady, turnstileReady } from "@/lib/env";
import { clientKey, json } from "@/lib/http";
import { internal, passthroughJson, unavailable } from "@/lib/internal";
import { apiLimiter } from "@/lib/limiter";
import { currentUser } from "@/lib/session";

export const dynamic = "force-dynamic";

/** The dashboard overview for the signed-in person. */
export async function GET(request: Request) {
  if (!apiLimiter.allow(clientKey(request))) return json(429, { ok: false, error: "rate_limited" });
  const user = currentUser(request);
  if (!user) {
    return json(401, { ok: false, error: "signed_out", oauth: oauthReady(), turnstile: turnstileReady() ? env.turnstileSiteKey() : "" });
  }
  try {
    return await passthroughJson(await internal("/internal/me", { user }), { oauth: oauthReady() });
  } catch {
    return unavailable();
  }
}
