import { timingSafeEqual } from "node:crypto";
import { exchangeCode } from "@/lib/discord";
import { clientKey, redirect } from "@/lib/http";
import { oauthLimiter } from "@/lib/limiter";
import { SESSION_COOKIE, SESSION_TTL, STATE_COOKIE, cookieHeader, readCookies, sign, verify } from "@/lib/session";

export const dynamic = "force-dynamic";

function same(a: string, b: string): boolean {
  const left = Buffer.from(a);
  const right = Buffer.from(b);
  return left.length === right.length && timingSafeEqual(left, right);
}

export async function GET(request: Request) {
  if (!oauthLimiter.allow(clientKey(request))) return redirect("/me/?error=rate_limited");
  const url = new URL(request.url);
  const state = url.searchParams.get("state") ?? "";
  const code = url.searchParams.get("code") ?? "";
  const expected = verify(readCookies(request)[STATE_COOKIE] ?? "");
  if (!expected || !state || !code || !same(String(expected.state ?? ""), state)) return redirect("/me/?error=state");

  let user;
  try {
    user = await exchangeCode(code);
  } catch (error) {
    console.warn("Discord sign-in failed:", error);
    return redirect("/me/?error=discord");
  }
  const response = redirect("/me/");
  response.headers.append("Set-Cookie", cookieHeader(SESSION_COOKIE, sign({ ...user, exp: Date.now() / 1000 + SESSION_TTL }), SESSION_TTL));
  response.headers.append("Set-Cookie", cookieHeader(STATE_COOKIE, "", 0));
  return response;
}
