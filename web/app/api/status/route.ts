import { clientKey, json } from "@/lib/http";
import { internal, passthrough, unavailable } from "@/lib/internal";
import { apiLimiter } from "@/lib/limiter";

/** The connect page asks this until the account is linked from outside the page, by the extension given its link. */
export async function GET(request: Request) {
  if (!apiLimiter.allow(clientKey(request))) return json(429, { connected: false, error: "rate_limited" });
  try {
    return passthrough(await internal("/internal/status", { query: new URL(request.url).searchParams }));
  } catch {
    return unavailable();
  }
}
