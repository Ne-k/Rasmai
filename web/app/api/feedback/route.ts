import { turnstileReady } from "@/lib/env";
import { clientKey, json, parseBody, sameOrigin } from "@/lib/http";
import { internal, passthrough, unavailable } from "@/lib/internal";
import { feedbackLimiter } from "@/lib/limiter";
import { verifyTurnstile } from "@/lib/turnstile";

/** The feedback form's answers. Anybody may send one, so it is counted per visitor and checked for a person before the bot hears of it. */
export async function POST(request: Request) {
  if (!sameOrigin(request)) return json(403, { ok: false, error: "cross_origin" });
  // the human check is the whole defence against bots, and it lets everything through when its keys are not set: fine on a laptop,
  // but in production that would leave the form open to anybody, so there it takes nothing until the keys are in
  if (!turnstileReady() && process.env.NODE_ENV === "production") return json(503, { ok: false, error: "check_unavailable" });
  const client = clientKey(request);
  if (!feedbackLimiter.allow(client)) return json(429, { ok: false, error: "rate_limited" });
  let body: Record<string, string>;
  try {
    body = await parseBody(request);
  } catch {
    return json(400, { ok: false, error: "bad_request" });
  }
  const rating = Number(body.rating);
  if (!Number.isInteger(rating) || rating < 1 || rating > 5) return json(400, { ok: false, error: "invalid_rating" });
  const verdict = await verifyTurnstile(body.token ?? "", client, "feedback");
  if (!verdict.ok) {
    console.info("turnstile rejected a feedback check:", verdict.codes.join(","));
    return json(400, { ok: false, error: "turnstile_failed" });
  }
  try {
    return passthrough(
      await internal("/internal/feedback", {
        method: "POST",
        client,
        body: { rating, liked: body.liked ?? "", annoyed: body.annoyed ?? "", wish: body.wish ?? "", contact: body.contact ?? "" },
      }),
    );
  } catch {
    return unavailable();
  }
}
