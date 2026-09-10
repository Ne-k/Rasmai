import { env, turnstileReady } from "@/lib/env";
import { clientKey, json } from "@/lib/http";
import { internal, passthroughJson, unavailable } from "@/lib/internal";
import { apiLimiter } from "@/lib/limiter";

export const dynamic = "force-dynamic";

/** What the connect page needs. The gateway link and the bookmark wait until the human check has passed. */
export async function GET(request: Request) {
  if (!apiLimiter.allow(clientKey(request))) return json(429, { ok: false, kind: "rate_limited" });
  const query = new URL(request.url).searchParams;
  let upstream: Response;
  try {
    upstream = await internal("/internal/connect-info", { query });
  } catch {
    return unavailable();
  }
  if (!upstream.ok) return passthroughJson(upstream);
  const info = (await upstream.json()) as Record<string, unknown>;
  const gated = turnstileReady() && !info.verified;
  return json(200, {
    ...info,
    loginLink: gated ? "" : info.loginLink,
    bookmarklet: gated ? "" : info.bookmarklet,
    verified: !gated,
    turnstile: turnstileReady() ? env.turnstileSiteKey() : "",
  });
}
