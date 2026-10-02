import { clientKey, parseBody, redirect, sameOrigin } from "@/lib/http";
import { internal } from "@/lib/internal";
import { oauthLimiter } from "@/lib/limiter";
import { clearPendingCookie, pendingOf } from "@/lib/pending";
import { currentUser } from "@/lib/session";
import { profileOf, sessionCookie } from "@/lib/signin";

/** The /merge/ form: two accounts of one person, each with a linked maimai, and the one whose scores stay. */
export async function POST(request: Request) {
  if (!sameOrigin(request)) return redirect("/me/?error=state");
  if (!oauthLimiter.allow(clientKey(request))) return redirect("/me/?error=rate_limited");
  const pending = pendingOf(request);
  const merge = pending?.merge;
  if (!pending || !merge) return redirect("/me/");
  // the Discord side has just proved itself by signing in, and the signed pending cookie only exists because the bot asked
  // this question; the site account is the signed-in session, or was matched by its verified email when nobody was signed in
  const user = currentUser(request);
  const joining = pending.identities.find((i) => i.provider === "discord" && i.subject === merge.to);
  if (!joining && (!user || (user.id !== merge.from && user.id !== merge.to))) return redirect("/me/?error=state");
  let body: Record<string, string> = {};
  try {
    body = await parseBody(request);
  } catch {
    body = {};
  }
  if (body.keep !== "from" && body.keep !== "to") return redirect("/merge/");

  let upstream: Response;
  try {
    upstream = await internal("/internal/auth/merge", {
      method: "POST",
      client: clientKey(request),
      body: {
        from: merge.from,
        to: merge.to,
        keep: body.keep,
        ...(joining ? { identity: { provider: joining.provider, subject: joining.subject, email: joining.email, emailVerified: joining.emailVerified } } : {}),
      },
    });
  } catch {
    return redirect("/me/?error=signin");
  }
  const answer = upstream.ok ? ((await upstream.json().catch(() => ({}))) as { userId?: string }) : {};
  if (answer.userId !== merge.to) return redirect(upstream.status === 409 ? "/me/?error=identity_taken" : "/me/?error=signin");

  const response = redirect("/me/");
  response.headers.append("Set-Cookie", sessionCookie(joining ? profileOf(merge.to, [joining]) : { ...user!, id: merge.to }));
  response.headers.append("Set-Cookie", clearPendingCookie());
  return response;
}
