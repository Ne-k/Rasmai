import { clientKey, json } from "@/lib/http";
import { internal, passthrough, unavailable } from "@/lib/internal";
import { apiLimiter } from "@/lib/limiter";

export const dynamic = "force-dynamic";

/** Whether maimai DX NET is in maintenance or not answering, so pages can say the data shown is the last read. */
export async function GET(request: Request) {
  if (!apiLimiter.allow(clientKey(request))) return json(429, { ok: false, error: "rate_limited" });
  try {
    return passthrough(await internal("/internal/servers"));
  } catch {
    return unavailable();
  }
}
