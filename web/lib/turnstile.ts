import { env, turnstileReady } from "./env";

// Cloudflare Turnstile: the widget hands the browser a token; only the server can turn it
// into a verdict. Tokens live five minutes and verify once.
const SITEVERIFY = "https://challenges.cloudflare.com/turnstile/v0/siteverify";

export type Verdict = { ok: boolean; codes: string[] };

export async function verifyTurnstile(token: string, remoteIp: string, action: string): Promise<Verdict> {
  if (!turnstileReady()) return { ok: true, codes: [] };
  const clean = (token ?? "").trim();
  if (!clean || clean.length > 2048) return { ok: false, codes: ["missing-input-response"] };
  const form = new URLSearchParams({ secret: env.turnstileSecret(), response: clean });
  if (remoteIp && remoteIp !== "local") form.set("remoteip", remoteIp);
  try {
    const response = await fetch(SITEVERIFY, {
      method: "POST",
      body: form,
      signal: AbortSignal.timeout(10000),
      cache: "no-store",
    });
    const result = (await response.json()) as { success?: boolean; action?: string; "error-codes"?: string[] };
    const codes = (result["error-codes"] ?? []).map(String);
    if (!result.success) return { ok: false, codes: codes.length ? codes : ["invalid-input-response"] };
    if (action && result.action && result.action !== action) return { ok: false, codes: ["action-mismatch"] };
    return { ok: true, codes: [] };
  } catch (error) {
    console.warn("turnstile siteverify unreachable:", error);
    return { ok: false, codes: ["internal-error"] };
  }
}
