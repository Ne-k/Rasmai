import { clientKey, parseBody, redirect, sameOrigin } from "@/lib/http";
import { internal } from "@/lib/internal";
import { oauthLimiter } from "@/lib/limiter";
import { clearPendingCookie, pendingOf } from "@/lib/pending";
import { POLICY_VERSION } from "@/lib/policy";
import { profileOf, sessionCookie } from "@/lib/signin";

/** The /welcome/ form: someone new has read the terms and privacy policy and agreed, so their account is made now. */
export async function POST(request: Request) {
  if (!sameOrigin(request)) return redirect("/me/?error=state");
  if (!oauthLimiter.allow(clientKey(request))) return redirect("/me/?error=rate_limited");
  const pending = pendingOf(request);
  if (!pending) return redirect("/welcome/");
  if (pending.merge) return redirect("/merge/");
  let body: Record<string, string> = {};
  try {
    body = await parseBody(request);
  } catch {
    body = {};
  }
  if (body.terms !== "on") return redirect("/welcome/");

  let upstream: Response;
  try {
    upstream = await internal("/internal/auth/create", {
      method: "POST",
      client: clientKey(request),
      body: {
        identities: pending.identities.map(({ provider, subject, email, emailVerified }) => ({ provider, subject, email, emailVerified })),
        termsVersion: POLICY_VERSION,
      },
    });
  } catch {
    return redirect("/me/?error=signin");
  }
  const answer = upstream.ok ? ((await upstream.json().catch(() => ({}))) as { userId?: string }) : {};
  const userId = String(answer.userId ?? "");
  if (!/^(\d{5,25}|w[0-9a-f]{20})$/.test(userId)) return redirect(upstream.status === 409 ? "/me/?error=identity_taken" : "/me/?error=signin");

  // a new account has no maimai linked yet, so the dashboard opens on that step
  const response = redirect("/me/?setup=1");
  response.headers.append("Set-Cookie", sessionCookie(profileOf(userId, pending.identities)));
  response.headers.append("Set-Cookie", clearPendingCookie());
  return response;
}
