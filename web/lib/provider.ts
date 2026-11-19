import { NextResponse } from "next/server";
import { turnstileReady } from "./env";
import { clientKey, json, parseBody } from "./http";
import { internal, passthrough, unavailable } from "./internal";
import { apiLimiter } from "./limiter";

/** For the OAuth routes the extension's approval window and other apps call: no cookie of this site is read, so any origin
 *  may read the answer, and nothing in between may keep it. */
export function open(response: NextResponse): NextResponse {
  response.headers.set("Access-Control-Allow-Origin", "*");
  response.headers.set("Access-Control-Allow-Headers", "Authorization, Content-Type");
  response.headers.set("Cache-Control", "no-store");
  return response;
}

export function preflight(methods: string): NextResponse {
  return open(new NextResponse(null, { status: 204, headers: { "Access-Control-Allow-Methods": methods } }));
}

/** The approval window's answer for a ticket. It comes as a form, so the extension's request needs no preflight. */
export async function decide(request: Request, step: "approve" | "deny"): Promise<NextResponse> {
  if (!apiLimiter.allow(clientKey(request))) return open(json(429, { ok: false, error: "rate_limited" }));
  let form: Record<string, string>;
  try {
    form = await parseBody(request);
  } catch {
    return open(json(400, { ok: false, error: "bad_request" }));
  }
  const expires = Math.floor(Number(form.expires));
  // the human check counts for a request of Rasmai's own, which links an account, as it does for a pasted sign-in
  const body = step === "deny" ? { ticket: form.ticket ?? "" }
    : { ticket: form.ticket ?? "", clal: (form.clal ?? "").trim(), ...(expires > 0 ? { expires } : {}), requireVerified: turnstileReady() };
  try {
    return open(passthrough(await internal(`/internal/oauth/${step}`, { method: "POST", client: clientKey(request), body })));
  } catch {
    return open(unavailable());
  }
}
