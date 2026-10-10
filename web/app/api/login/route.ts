import { turnstileReady } from "@/lib/env";
import { clientKey, json, parseBody, redirect, wantsHtml } from "@/lib/http";
import { internal, unavailable } from "@/lib/internal";

type LoginResult = {
  ok: boolean;
  kind?: string;
  error?: string;
  region?: string;
  player?: { name?: string; rating?: number | string };
};

/**
 * A login hand-off. International: the bookmarklet's form post from SEGA's gateway page, carrying its session cookie.
 * Japan: the connect page's SEGA ID form, posted as JSON. The bot proves the sign-in works and links the account.
 */
export async function POST(request: Request) {
  const html = wantsHtml(request);
  const client = clientKey(request);
  let body: Record<string, string> = {};
  // the link it came from rides along, so an error the same link can get past offers a way back to it
  const fail = (status: number, kind: string, message: string) =>
    html
      ? redirect(`/error/?${new URLSearchParams({ kind, ...(body.code && body.user ? { code: body.code, user: body.user } : {}) })}`)
      : json(status, { ok: false, kind, error: message });

  try {
    body = await parseBody(request);
  } catch (error) {
    return fail(400, "no_login", `invalid request: ${String(error)}`);
  }
  let upstream: Response;
  try {
    upstream = await internal("/internal/login", {
      method: "POST",
      client,
      body: {
        code: body.code ?? "",
        user: body.user ?? "",
        token: body.token ?? "",
        region: body.region ?? "intl",
        // Japan only: typed on the connect page, passed straight through and never kept here
        segaId: body.segaId ?? "",
        password: body.password ?? "",
        aime: body.aime ?? "",
        requireVerified: turnstileReady(),
      },
    });
  } catch {
    return html ? redirect("/error/?kind=unknown") : unavailable();
  }
  let result: LoginResult;
  try {
    result = (await upstream.json()) as LoginResult;
  } catch {
    return fail(502, "unknown", "the bot answered with something unexpected");
  }
  if (!result.ok) return fail(upstream.status, result.kind ?? "unknown", result.error ?? "sign-in failed");
  if (html) {
    const done = new URLSearchParams({
      player: String(result.player?.name ?? ""),
      region: String(result.region ?? ""),
      rating: String(result.player?.rating ?? ""),
    });
    return redirect(`/connected/?${done}`);
  }
  return json(200, result);
}
