import { clientKey, json } from "@/lib/http";
import { internal, passthrough, unavailable } from "@/lib/internal";
import { apiLimiter } from "@/lib/limiter";

type Params = { params: Promise<{ id: string }> };

/** An application's picture: the bot's own redrawing of what the developer sent, never the file itself. Like every answer
 *  of the site it goes out with nosniff (next.config.ts), so a browser takes it as the PNG it says it is and nothing else. */
export async function GET(request: Request, { params }: Params) {
  if (!apiLimiter.allow(clientKey(request))) return json(429, { ok: false, error: "rate_limited" });
  const { id } = await params;
  if (!/^[A-Za-z0-9_-]{24}$/.test(id)) return json(404, { ok: false, error: "not_found" });
  try {
    const response = passthrough(await internal(`/internal/oauth/icon/${id}`));
    // the extension's approval window reads the picture, to check it against the mark in the request the site signed
    response.headers.set("Access-Control-Allow-Origin", "*");
    return response;
  } catch {
    return unavailable();
  }
}
