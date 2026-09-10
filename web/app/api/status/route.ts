import { clientKey, json } from "@/lib/http";
import { internal, passthrough, unavailable } from "@/lib/internal";
import { apiLimiter } from "@/lib/limiter";

export const dynamic = "force-dynamic";

/** The connect page polls this until the bookmark has handed the session over. */
export async function GET(request: Request) {
  if (!apiLimiter.allow(clientKey(request))) return json(429, { connected: false, error: "rate_limited" });
  try {
    return passthrough(await internal("/internal/status", { query: new URL(request.url).searchParams }));
  } catch {
    return unavailable();
  }
}
