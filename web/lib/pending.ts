import { cookieHeader, readCookies, sign, verify } from "./session";

export const PENDING_COOKIE = "rasmai_pending";
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

type Jar = { get(name: string): { value: string } | undefined };

/** Who has signed in but not finished: the identities waiting for terms, or the two accounts waiting for a choice. */
export function readPending(jar: Jar): Pending | null {
  const raw = jar.get(PENDING_COOKIE)?.value;
  const payload = raw ? verify(raw) : null;
  if (!payload || !Array.isArray(payload.identities)) return null;
  const identities = (payload.identities as PendingIdentity[]).filter(
    (i) => i && (i.provider === "discord" || i.provider === "google") && typeof i.subject === "string" && i.subject,
  );
  if (!identities.length) return null;
  return { identities, merge: payload.merge as Pending["merge"] };
}

/** The same jar, read from a route handler's request. */
export function pendingOf(request: Request): Pending | null {
  const cookies = readCookies(request);
  return readPending({ get: (name) => (name in cookies ? { value: cookies[name] } : undefined) });
}

export function pendingCookie(pending: Pending): string {
  return cookieHeader(PENDING_COOKIE, sign({ ...pending, exp: Date.now() / 1000 + PENDING_TTL }), PENDING_TTL);
}

export function clearPendingCookie(): string {
  return cookieHeader(PENDING_COOKIE, "", 0);
}
