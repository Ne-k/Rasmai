import { NextResponse } from "next/server";
import { env } from "./env";
import type { DiscordUser } from "./session";

type Options = {
  method?: "GET" | "POST";
  body?: unknown;
  user?: DiscordUser | null;
  client?: string;
  query?: URLSearchParams | string;
};

/** One call to the bot's internal API: shared secret, the signed-in user, and the visitor's address. */
export async function internal(path: string, options: Options = {}): Promise<Response> {
  const headers: Record<string, string> = { Accept: "application/json" };
  const secret = env.internalSecret();
  if (secret) headers["X-Rasmai-Internal"] = secret;
  if (options.user) headers["X-Rasmai-User"] = JSON.stringify(options.user);
  if (options.client) headers["X-Rasmai-Client"] = options.client;
  let body: string | undefined;
  if (options.body !== undefined) {
    headers["Content-Type"] = "application/json";
    body = JSON.stringify(options.body);
  }
  const query = options.query ? `?${options.query.toString()}` : "";
  return fetch(`${env.internalUrl()}${path}${query}`, {
    method: options.method ?? "GET",
    headers,
    body,
    cache: "no-store",
    signal: AbortSignal.timeout(120000),
  });
}

// content-encoding is deliberately not forwarded: fetch has already decompressed the body
const FORWARDED = ["content-type", "content-disposition", "cache-control"];

/** Hand the bot's answer to the browser as it came, status and body included. */
export function passthrough(upstream: Response): NextResponse {
  const headers = new Headers();
  for (const name of FORWARDED) {
    const value = upstream.headers.get(name);
    if (value) headers.set(name, value);
  }
  if (!headers.has("cache-control")) headers.set("cache-control", "no-store");
  return new NextResponse(upstream.body, { status: upstream.status, headers });
}

/** Like passthrough, but for JSON answers the web server adds fields to. */
export async function passthroughJson(upstream: Response, extra: Record<string, unknown> = {}): Promise<NextResponse> {
  let payload: Record<string, unknown> = {};
  try {
    payload = (await upstream.json()) as Record<string, unknown>;
  } catch {
    payload = { ok: false, error: "bad_upstream" };
  }
  return NextResponse.json({ ...payload, ...extra }, { status: upstream.status, headers: { "Cache-Control": "no-store" } });
}

export function unavailable(): NextResponse {
  return NextResponse.json({ ok: false, error: "bot_unreachable" }, { status: 503, headers: { "Cache-Control": "no-store" } });
}
