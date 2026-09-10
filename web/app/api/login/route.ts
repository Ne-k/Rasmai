import { turnstileReady } from "@/lib/env";
import { clientKey, json, parseBody, redirect, wantsHtml } from "@/lib/http";
import { internal, unavailable } from "@/lib/internal";

export const dynamic = "force-dynamic";

type LoginResult = {
  ok: boolean;
  kind?: string;
  error?: string;
  region?: string;
  player?: { name?: string; rating?: number | string };
};

/** The bookmarklet's hand-off, posted as a form from SEGA's gateway page. The bot validates the session and links the account. */
export async function POST(request: Request) {
  const html = wantsHtml(request);
  const client = clientKey(request);
  const fail = (status: number, kind: string, message: string) =>
    html ? redirect(`/error/?kind=${encodeURIComponent(kind)}`) : json(status, { ok: false, error: message });

  let body: Record<string, string>;
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
      body: { code: body.code ?? "", user: body.user ?? "", token: body.token ?? "", region: body.region ?? "intl", requireVerified: turnstileReady() },
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
