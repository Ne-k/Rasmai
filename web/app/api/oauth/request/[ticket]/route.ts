import { clientKey, json } from "@/lib/http";
import { internal, passthrough, unavailable } from "@/lib/internal";
import { apiLimiter } from "@/lib/limiter";
import { open } from "@/lib/provider";

type Params = { params: Promise<{ ticket: string }> };

// The app behind a ticket, for the extension's approval window: it shows what Rasmai says, not what the page said.
export async function GET(request: Request, { params }: Params) {
  if (!apiLimiter.allow(clientKey(request))) return open(json(429, { ok: false, error: "rate_limited" }));
  const { ticket } = await params;
  if (!/^[A-Za-z0-9_-]{1,64}$/.test(ticket)) return open(json(404, { ok: false, error: "expired" }));
  try {
    return open(passthrough(await internal("/internal/oauth/request", { query: new URLSearchParams({ ticket }) })));
  } catch {
    return open(unavailable());
  }
}
