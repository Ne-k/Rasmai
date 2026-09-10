import { createHmac, randomBytes, timingSafeEqual } from "node:crypto";
import { isSecure } from "./env";

export const SESSION_COOKIE = "rasmai_session";
export const STATE_COOKIE = "rasmai_oauth";
export const SESSION_TTL = 30 * 24 * 3600;
export const STATE_TTL = 600;

export type DiscordUser = { id: string; name: string; handle: string; avatar: string };

let generated: string | null = null;

/** The HMAC key behind sessions. Set RASMAI_SESSION_SECRET; a generated one signs sessions out on every restart. */
function secret(): string {
  const configured = (process.env.RASMAI_SESSION_SECRET ?? process.env.MAIMAI_TOTP_SECRET ?? "").trim();
  if (configured) return configured;
  if (!generated) {
    generated = randomBytes(48).toString("base64url");
    console.warn("RASMAI_SESSION_SECRET is empty: dashboard sessions will not survive a restart");
  }
  return generated;
}

const b64 = (data: Buffer | string) => Buffer.from(data).toString("base64url");

export function sign(payload: Record<string, unknown>): string {
  const body = b64(JSON.stringify(payload));
  const mac = createHmac("sha256", secret()).update(body).digest();
  return `${body}.${b64(mac)}`;
}

export function verify(token: string): Record<string, unknown> | null {
  const dot = token.indexOf(".");
  if (dot < 1) return null;
  const body = token.slice(0, dot);
  const given = Buffer.from(token.slice(dot + 1), "base64url");
  const expected = createHmac("sha256", secret()).update(body).digest();
  if (given.length !== expected.length || !timingSafeEqual(given, expected)) return null;
  try {
    const payload = JSON.parse(Buffer.from(body, "base64url").toString("utf-8")) as Record<string, unknown>;
    if (Number(payload.exp ?? 0) < Date.now() / 1000) return null;
    return payload;
  } catch {
    return null;
  }
}

export function cookieHeader(name: string, value: string, maxAge: number): string {
  const secure = isSecure() ? "; Secure" : "";
  return `${name}=${value}; Path=/; Max-Age=${maxAge}; HttpOnly; SameSite=Lax${secure}`;
}

export function readCookies(request: Request): Record<string, string> {
  const jar: Record<string, string> = {};
  for (const part of (request.headers.get("cookie") ?? "").split(";")) {
    const eq = part.indexOf("=");
    if (eq > 0) jar[part.slice(0, eq).trim()] = part.slice(eq + 1).trim();
  }
  return jar;
}

/** The signed-in Discord user, or null. */
export function currentUser(request: Request): DiscordUser | null {
  const token = readCookies(request)[SESSION_COOKIE];
  if (!token) return null;
  const payload = verify(token);
  if (!payload || typeof payload.id !== "string") return null;
  return {
    id: payload.id,
    name: String(payload.name ?? ""),
    handle: String(payload.handle ?? ""),
    avatar: String(payload.avatar ?? ""),
  };
}
