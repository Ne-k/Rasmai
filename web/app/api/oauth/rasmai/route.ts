import { turnstileReady } from "@/lib/env";
import { clientKey, json, parseBody } from "@/lib/http";
import { internal, passthrough, unavailable } from "@/lib/internal";
import { apiLimiter } from "@/lib/limiter";

// What the link page asks for its "link with the extension" button: a request of Rasmai's own for this player, as a link to
// the consent page. The login code is what is trusted, as it is when a sign-in is pasted, so the human check counts here too.
export async function POST(request: Request) {
  if (!apiLimiter.allow(clientKey(request))) return json(429, { ok: false, kind: "rate_limited", error: "Too many tries. Wait a minute." });
  let form: Record<string, string>;
  try {
    form = await parseBody(request);
  } catch {
    return json(400, { ok: false, kind: "bad_request", error: "The body must be form-encoded or JSON." });
  }
  try {
    return passthrough(await internal("/internal/oauth/rasmai", {
      method: "POST",
      client: clientKey(request),
      body: { code: form.code ?? "", user: form.user ?? "", requireVerified: turnstileReady() },
    }));
  } catch {
    return unavailable();
  }
}
