import { randomBytes, timingSafeEqual } from "node:crypto";
import { NextResponse } from "next/server";
import { turnstileReady } from "./env";
import { clientKey, parseBody, redirect, sameOrigin } from "./http";
import { isUserId, isWebId } from "./ids";
import { internal } from "./internal";
import { clearPendingCookie, pendingCookie, pendingOf, type Pending, type PendingIdentity, type Summary } from "./pending";
import { SESSION_COOKIE, SESSION_TTL, STATE_COOKIE, STATE_TTL, cookieHeader, currentUser, readCookies, sign, verify, type DiscordUser } from "./session";
import { verifyTurnstile } from "./turnstile";

export type Provider = "discord" | "google";

/** What a sign-in in flight remembers, in the signed state cookie. `link` is the signed-in account it attaches to. */
type Flow = { provider: Provider; state: string; verifier: string; nonce: string; link: string; keep: boolean; retried: boolean };

export function same(a: string, b: string): boolean {
  const left = Buffer.from(a);
  const right = Buffer.from(b);
  return left.length === right.length && timingSafeEqual(left, right);
}

export function newFlow(provider: Provider, link: string, keep: boolean, retried = false): Flow {
  const random = (bytes: number) => randomBytes(bytes).toString("base64url");
  return { provider, state: random(24), verifier: provider === "google" ? random(48) : "", nonce: provider === "google" ? random(24) : "", link, keep, retried };
}

export function withFlow(response: NextResponse, flow: Flow): NextResponse {
  response.headers.append("Set-Cookie", cookieHeader(STATE_COOKIE, sign({ ...flow, exp: Date.now() / 1000 + STATE_TTL }), STATE_TTL));
  return response;
}

/** The flow this browser started, if the state the provider sent back is the one in its cookie. */
export function readFlow(request: Request, provider: Provider, state: string): Flow | null {
  const saved = verify(readCookies(request)[STATE_COOKIE] ?? "");
  if (!saved || !state || saved.provider !== provider || !same(String(saved.state ?? ""), state)) return null;
  return {
    provider,
    state,
    verifier: String(saved.verifier ?? ""),
    nonce: String(saved.nonce ?? ""),
    link: String(saved.link ?? ""),
    keep: saved.keep === true,
    retried: saved.retried === true,
  };
}

/** Back to the dashboard, with the one-time state spent. */
export function back(error = ""): NextResponse {
  const response = redirect(error ? `/me/?error=${error}` : "/me/");
  response.headers.append("Set-Cookie", cookieHeader(STATE_COOKIE, "", 0));
  return response;
}

function begin(provider: Provider, link: string, keep: boolean, authorize: (flow: Flow) => string): NextResponse {
  const flow = newFlow(provider, link, keep);
  return withFlow(redirect(authorize(flow)), flow);
}

/** Start a sign-in. Linking from a signed-in session and carrying on after /welcome/ skip the human check, because
 * a session or a signed pending cookie already proves one was passed. */
export async function startSignIn(request: Request, provider: Provider, ready: boolean, authorize: (flow: Flow) => string): Promise<NextResponse> {
  const post = request.method === "POST";
  if (post && !sameOrigin(request)) return redirect("/me/?error=state");
  if (!ready) return redirect("/me/?error=oauth_unconfigured");
  const query = new URL(request.url).searchParams;
  const link = query.get("link") === "1" ? (currentUser(request)?.id ?? "") : "";
  const keep = query.get("keep") === "pending" && pendingOf(request) !== null;
  if (link || keep) return begin(provider, link, keep, authorize);
  if (!post) return turnstileReady() ? redirect("/me/") : begin(provider, "", false, authorize); // with the widget on, a sign-in is a form post carrying its token
  let body: Record<string, string> = {};
  try {
    body = await parseBody(request);
  } catch {
    body = {};
  }
  const verdict = await verifyTurnstile(body["cf-turnstile-response"] ?? "", clientKey(request), "dashboard");
  if (!verdict.ok) {
    console.info("turnstile rejected a dashboard sign-in:", verdict.codes.join(","));
    return redirect("/me/?error=verify");
  }
  return begin(provider, "", false, authorize);
}

type Resolved =
  | { status: "signed_in"; userId: string }
  | { status: "needs_terms" }
  | { status: "needs_choice"; from: string; to: string; fromSummary: Summary; toSummary: Summary }
  | { status: "identity_taken" | "failed" };

const summary = (value: unknown): Summary => {
  const s = (value ?? {}) as Record<string, unknown>;
  return { player: String(s.player ?? "").slice(0, 64), rating: typeof s.rating === "number" ? s.rating : null, region: String(s.region ?? "").slice(0, 8) };
};

async function resolve(identity: PendingIdentity, sessionUserId: string, client: string): Promise<Resolved> {
  let upstream: Response;
  try {
    const body: Record<string, unknown> = { provider: identity.provider, subject: identity.subject, email: identity.email, emailVerified: identity.emailVerified };
    if (sessionUserId) body.sessionUserId = sessionUserId;
    upstream = await internal("/internal/auth/resolve", { method: "POST", body, client });
  } catch {
    return { status: "failed" };
  }
  if (upstream.status === 409) return { status: "identity_taken" };
  if (!upstream.ok) return { status: "failed" };
  const answer = (await upstream.json().catch(() => ({}))) as Record<string, unknown>;
  if (answer.status === "needs_terms") return { status: "needs_terms" };
  if (answer.status === "signed_in" && isUserId(String(answer.userId))) return { status: "signed_in", userId: String(answer.userId) };
  if (answer.status === "needs_choice" && isWebId(String(answer.from)) && /^\d{5,25}$/.test(String(answer.to))) {
    return { status: "needs_choice", from: String(answer.from), to: String(answer.to), fromSummary: summary(answer.fromSummary), toSummary: summary(answer.toSummary) };
  }
  return { status: "failed" };
}

export function sessionCookie(user: DiscordUser): string {
  return cookieHeader(SESSION_COOKIE, sign({ ...user, exp: Date.now() / 1000 + SESSION_TTL }), SESSION_TTL);
}

/** The name, handle and picture the dashboard shows: Discord's when the account has one, since Google gives no avatar. */
export function profileOf(userId: string, identities: PendingIdentity[]): DiscordUser {
  const shown = identities.find((i) => i.provider === "discord") ?? identities[0];
  return { id: userId, name: shown.name, handle: shown.handle, avatar: shown.avatar };
}

/** Every sign-in ends here: ask the bot who this identity is and do what it says. */
export async function finishSignIn(request: Request, flow: Flow, identity: PendingIdentity): Promise<NextResponse> {
  if (flow.link && currentUser(request)?.id !== flow.link) return back("state");
  const client = clientKey(request);
  const waiting = flow.keep ? (pendingOf(request)?.identities ?? []).filter((i) => i.provider !== identity.provider) : [];

  const result = await resolve(identity, flow.link, client);
  if (result.status === "identity_taken") return back("identity_taken");
  if (result.status === "failed") return back("signin");

  if (result.status === "signed_in") {
    // the sign-in that came first belongs to the same person: it joins this account
    let taken = false;
    for (const other of waiting) {
      const joined = await resolve(other, result.userId, client);
      if (joined.status !== "signed_in" || joined.userId !== result.userId) taken = true;
    }
    const response = back(taken ? "identity_taken" : "");
    response.headers.append("Set-Cookie", sessionCookie(profileOf(result.userId, [identity, ...waiting])));
    response.headers.append("Set-Cookie", clearPendingCookie());
    return response;
  }
  const next: Pending = { identities: [...waiting, identity] };
  if (result.status === "needs_choice") {
    next.merge = { from: result.from, to: result.to, fromSummary: result.fromSummary, toSummary: result.toSummary };
  }
  const response = redirect(result.status === "needs_choice" ? "/merge/" : "/welcome/");
  response.headers.append("Set-Cookie", pendingCookie(next));
  response.headers.append("Set-Cookie", cookieHeader(STATE_COOKIE, "", 0));
  return response;
}
