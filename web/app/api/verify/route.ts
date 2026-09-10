import { clientKey, json, parseBody, sameOrigin } from "@/lib/http";
import { internal, passthrough, unavailable } from "@/lib/internal";
import { verifyLimiter } from "@/lib/limiter";
import { verifyTurnstile } from "@/lib/turnstile";

export const dynamic = "force-dynamic";

/** The connect page's Turnstile token. Verified with Cloudflare here, then remembered on the login code by the bot. */
export async function POST(request: Request) {
  if (!sameOrigin(request)) return json(403, { ok: false, error: "cross_origin" });
  const client = clientKey(request);
  if (!verifyLimiter.allow(client)) return json(429, { ok: false, error: "rate_limited" });
  let body: Record<string, string>;
  try {
    body = await parseBody(request);
  } catch (error) {
    return json(400, { ok: false, error: `invalid_request: ${String(error)}` });
  }
  const verdict = await verifyTurnstile(body.token ?? "", client, "connect");
  if (!verdict.ok) {
    console.info("turnstile rejected a connect check:", verdict.codes.join(","));
    return json(400, { ok: false, error: "turnstile_failed", codes: verdict.codes });
  }
  try {
    return passthrough(await internal("/internal/verify", { method: "POST", body: { code: body.code ?? "", user: body.user ?? "" }, client }));
  } catch {
    return unavailable();
  }
}
