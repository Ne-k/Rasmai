import { NextResponse } from "next/server";
import { env } from "./env";

/** The visitor's address, for per-client limits.

 * Behind Cloudflare (MAIMAI_BEHIND_CLOUDFLARE) it states the address outright in CF-Connecting-IP.
 * Behind anything else that header is whatever the client chose to send, so it is ignored unless the
 * flag says Cloudflare is the only way in. Failing that, the *last* hop of X-Forwarded-For is the one
 * the proxy in front of us appended; the first hop is client-chosen too, and keying a limiter on
 * either would let one client pick a fresh key per request. */
export function clientKeyFromHeaders(headers: Headers): string {
  if (env.behindCloudflare()) {
    const cloudflare = (headers.get("cf-connecting-ip") ?? "").trim();
    if (cloudflare) return cloudflare;
  }
  const forwarded = (headers.get("x-forwarded-for") ?? "").split(",").map((hop) => hop.trim()).filter(Boolean);
  if (forwarded.length) return forwarded[forwarded.length - 1];
  return (headers.get("x-real-ip") ?? "").trim() || "local";
}

export function clientKey(request: Request): string {
  return clientKeyFromHeaders(request.headers);
}

/** True when a POST came from our own pages.

 * Browsers state the relationship outright in Sec-Fetch-Site, which is the reliable signal:
 * Firefox sends `Origin: null` on same-origin posts under a strict referrer policy, so the
 * Origin header alone would refuse honest sign-ins. Origin is the fallback for old browsers. */
export function sameOrigin(request: Request): boolean {
  const site = request.headers.get("sec-fetch-site");
  if (site) return site === "same-origin" || site === "none";
  const origin = request.headers.get("origin");
  if (!origin || origin === "null") return false;
  try {
    const given = new URL(origin).host;
    const host = request.headers.get("host") ?? "";
    return given === new URL(env.publicUrl()).host || given === host;
  } catch {
    return false;
  }
}

export function json(status: number, body: unknown): NextResponse {
  return NextResponse.json(body, { status, headers: { "Cache-Control": "no-store" } });
}

export function redirect(location: string): NextResponse {
  return new NextResponse(null, { status: 303, headers: { Location: location, "Cache-Control": "no-store" } });
}

/** JSON or form body as a flat string map; bodies over 64 KB are refused. */
export async function parseBody(request: Request): Promise<Record<string, string>> {
  const length = Number(request.headers.get("content-length") ?? "0");
  if (length > 65536) throw new Error("request body too large");
  const type = request.headers.get("content-type") ?? "";
  const raw = await request.text();
  if (type.includes("application/json")) {
    const parsed = JSON.parse(raw || "{}") as Record<string, unknown>;
    return Object.fromEntries(Object.entries(parsed).map(([key, value]) => [key, String(value ?? "")]));
  }
  return Object.fromEntries(new URLSearchParams(raw).entries());
}

export function wantsHtml(request: Request): boolean {
  return (request.headers.get("accept") ?? "").includes("text/html");
}
