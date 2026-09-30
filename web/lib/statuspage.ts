import { createHash, timingSafeEqual } from "node:crypto";
import { NextResponse } from "next/server";
import { env } from "./env";
import { clientKey, json } from "./http";
import { internal } from "./internal";
import { apiLimiter } from "./limiter";

const digest = (value: string) => createHash("sha256").update(value).digest();

/** The bot's status payload for the caller who holds STATUSPAGE_TOKEN, or the response that turns everyone else away.
 *
 * No token configured means the endpoints do not exist, so a site that never set one exposes nothing.
 * The token is compared as two fixed-length digests, so neither its length nor a matching prefix shows in the timing. */
export async function statusFor(request: Request, path = "/internal/statuspage"): Promise<Record<string, any> | NextResponse> {
  const token = env.statuspageToken();
  if (!token) return json(404, { ok: false, error: "not_found" });
  if (!apiLimiter.allow(clientKey(request))) return json(429, { ok: false, error: "rate_limited" });
  const given = (request.headers.get("authorization") ?? "").replace(/^Bearer\s+/i, "");
  if (!timingSafeEqual(digest(given), digest(token))) return json(401, { ok: false, error: "unauthorized" });
  try {
    const upstream = await internal(path);
    if (upstream.ok) return (await upstream.json()) as Record<string, any>;
  } catch {
    // falls through: an unanswering bot is itself the status
  }
  return { ok: true, status: "major_outage", components: { bot: "major_outage" }, metrics: {}, days: [], recent: [] };
}
