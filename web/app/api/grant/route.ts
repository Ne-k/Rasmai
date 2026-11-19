import type { NextResponse } from "next/server";
import { clientKey, json } from "@/lib/http";
import { internal, unavailable } from "@/lib/internal";
import { apiLimiter } from "@/lib/limiter";

function open(response: NextResponse): NextResponse {
  response.headers.set("Access-Control-Allow-Origin", "*");
  return response;
}

// A verified bot's grant for the Aime sign-in helper (developers.rasmai.lol/docs/extension): `/api/grant?origin=https://your.site`. The grant is
// signed for that origin alone and is no secret, so anyone may ask; a site that is not on the list gets a 404.
export async function GET(request: Request) {
  if (!apiLimiter.allow(clientKey(request))) return open(json(429, { ok: false, error: "Too many tries. Wait a minute." }));
  const origin = new URL(request.url).searchParams.get("origin") ?? "";
  try {
    const upstream = await internal("/internal/grant", { query: new URLSearchParams({ origin }) });
    const answer = (await upstream.json()) as { ok?: boolean; grant?: string; name?: string; exp?: number; error?: string };
    if (!upstream.ok || !answer.ok) return open(json(404, { ok: false, error: answer.error ?? "That site is not a verified bot." }));
    return open(json(200, { ok: true, grant: answer.grant, name: answer.name, exp: answer.exp }));
  } catch {
    return open(unavailable());
  }
}
