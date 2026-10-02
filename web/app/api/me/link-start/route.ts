import { clientKey, json, parseBody, sameOrigin } from "@/lib/http";
import { internal, passthroughJson, unavailable } from "@/lib/internal";
import { apiLimiter } from "@/lib/limiter";
import { currentUser } from "@/lib/session";

/** A signed-in person asks for the link that connects their maimai account, whichever sign-in they used. */
export async function POST(request: Request) {
  if (!apiLimiter.allow(clientKey(request))) return json(429, { ok: false, error: "rate_limited" });
  if (!sameOrigin(request)) return json(403, { ok: false, error: "cross_origin" });
  const user = currentUser(request);
  if (!user) return json(401, { ok: false, error: "signed_out" });
  let region = "";
  try {
    region = (await parseBody(request)).region;
  } catch {
    region = "";
  }
  if (region !== "intl" && region !== "jp") return json(400, { ok: false, error: "bad_region" });
  try {
    return await passthroughJson(await internal("/internal/me/link-start", { method: "POST", user, client: clientKey(request), body: { region } }));
  } catch {
    return unavailable();
  }
}
