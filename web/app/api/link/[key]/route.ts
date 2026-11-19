import type { NextResponse } from "next/server";
import { turnstileReady } from "@/lib/env";
import { clientKey, json, parseBody } from "@/lib/http";
import { internal, unavailable } from "@/lib/internal";
import { apiLimiter } from "@/lib/limiter";

type Params = { params: Promise<{ key: string }> };

// Rasmai's end of the Aime sign-in helper's link protocol (developers.rasmai.lol/docs/extension): a link, `/api/link/<login code>.<user>`, that
// a person pastes into the extension. GET says the link is live; POST takes the gateway's sign-in as `clal` and links the
// account, exactly as the connect page's paste does. The key is the login code itself (192 random bits, single use, ten
// minutes) with the signed user id, so holding the link is the right to use it. No cookie of this site is read, which is why
// any origin may call it.
const KEY = /^([A-Za-z0-9_-]{20,64})\.([A-Za-z0-9_-]+\.[A-Za-z0-9_-]+)$/;

function open(response: NextResponse): NextResponse {
  response.headers.set("Access-Control-Allow-Origin", "*");
  return response;
}

async function parts(request: Request, params: Params["params"]) {
  if (!apiLimiter.allow(clientKey(request))) return { refused: open(json(429, { ok: false, error: "Too many tries. Wait a minute." })) };
  const match = KEY.exec((await params).key);
  if (!match) return { refused: open(json(404, { ok: false, error: "That isn't a Rasmai link." })) };
  return { code: match[1], user: match[2] };
}

export async function GET(request: Request, { params }: Params) {
  const key = await parts(request, params);
  if ("refused" in key) return key.refused;
  try {
    const upstream = await internal("/internal/connect-info", { query: new URLSearchParams({ code: key.code, user: key.user }) });
    const info = (await upstream.json()) as { ok?: boolean; method?: string; verified?: boolean; grant?: string };
    // a Japan code links with a SEGA ID on the connect page: there is no cookie to hand over
    if (!upstream.ok || !info.ok || info.method !== "cookie") {
      return open(json(404, { ok: false, error: "That link expired or was already used. Run /login in Discord for a new one." }));
    }
    return open(json(200, { aimeLink: 1, grant: info.grant ?? "", ready: !turnstileReady() || Boolean(info.verified), wait: "Pass the check on your Rasmai link page first, then try again." }));
  } catch {
    return open(unavailable());
  }
}

export async function POST(request: Request, { params }: Params) {
  const key = await parts(request, params);
  if ("refused" in key) return key.refused;
  let clal = "";
  try {
    clal = ((await parseBody(request)).clal ?? "").trim();
  } catch {
    clal = "";
  }
  if (!/^[A-Za-z0-9]{64}$/.test(clal)) return open(json(400, { ok: false, error: "That's not a valid sign-in." }));
  try {
    const upstream = await internal("/internal/login", {
      method: "POST",
      client: clientKey(request),
      body: { code: key.code, user: key.user, token: clal, region: "intl", requireVerified: turnstileReady() },
    });
    const result = (await upstream.json()) as { ok?: boolean; error?: string; player?: { name?: string } };
    if (!upstream.ok || !result.ok) return open(json(upstream.status >= 400 ? upstream.status : 400, { ok: false, error: result.error ?? "The sign-in didn't work." }));
    return open(json(200, { ok: true, player: result.player?.name ?? "" }));
  } catch {
    return open(unavailable());
  }
}
