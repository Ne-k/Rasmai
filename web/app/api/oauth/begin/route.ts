import { clientKey, json } from "@/lib/http";
import { internal, passthrough, unavailable } from "@/lib/internal";
import { apiLimiter } from "@/lib/limiter";

// What the consent page (app/oauth/authorize) asks first: the authorize request as it came, for the bot to judge and to
// answer with the app and a ticket for the extension.
export async function GET(request: Request) {
  if (!apiLimiter.allow(clientKey(request))) return json(429, { ok: false, error: "rate_limited" });
  try {
    return passthrough(await internal("/internal/oauth/begin", { query: new URL(request.url).searchParams }));
  } catch {
    return unavailable();
  }
}
