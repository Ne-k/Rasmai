import { cookieHeader, readCookies, sign, verify } from "./session";

export const PENDING_COOKIE = "rasmai_pending";
// ponytail: the pending cookie holds the raw email for these ten minutes, signed but not encrypted; seal it or keep only the hash server-side if it ever has to outlive the sign-in
const PENDING_TTL = 600;

export type Summary = { player: string; rating: number | null; region: string };
export type PendingIdentity = {
  provider: "discord" | "google";
  subject: string;
  email: string;
  emailVerified: boolean;
  name: string;
  handle: string;
  avatar: string;
};
export type Pending = { identities: PendingIdentity[]; merge?: { from: string; to: string; fromSummary: Summary; toSummary: Summary } };

/** Who has signed in but not finished: the identities waiting for terms, or the two accounts waiting for a choice. */
export function readPending(token: string | undefined): Pending | null {
  const payload = token ? verify(token) : null;
  if (!payload || !Array.isArray(payload.identities)) return null;
  const identities = (payload.identities as PendingIdentity[]).filter(
    (i) => i && (i.provider === "discord" || i.provider === "google") && typeof i.subject === "string" && i.subject,
  );
  if (!identities.length) return null;
  return { identities, merge: payload.merge as Pending["merge"] };
}

/** The same, read from a route handler's request. */
export function pendingOf(request: Request): Pending | null {
  return readPending(readCookies(request)[PENDING_COOKIE]);
}

export function pendingCookie(pending: Pending): string {
  return cookieHeader(PENDING_COOKIE, sign({ ...pending, exp: Date.now() / 1000 + PENDING_TTL }), PENDING_TTL);
}

export function clearPendingCookie(): string {
  return cookieHeader(PENDING_COOKIE, "", 0);
}
