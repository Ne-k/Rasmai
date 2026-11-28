import { clientKey, redirect } from "@/lib/http";
import { internal } from "@/lib/internal";
import { oauthLimiter } from "@/lib/limiter";

const STATE = /^[A-Za-z0-9_-]{16,64}$/;

function failed(error: string) {
  console.warn("Kamaitachi callback failed:", error);
  return redirect(`/me/?error=${error}`);
}

export async function GET(request: Request) {
  const client = clientKey(request);
  if (!oauthLimiter.allow(client)) return redirect("/me/?error=rate_limited");
  const query = new URL(request.url).searchParams;
  const code = query.get("code") ?? "";
  const context = query.get("context") ?? "";
  if (context.length > 512 || !STATE.test(context)) return failed("kamaitachi_expired");
  if (!code || code.length > 512) return failed("kamaitachi");
  // no user is sent: the state alone names the account, since the link can start in Discord with no site session
  let upstream: Response;
  try {
    upstream = await internal("/internal/kamaitachi/callback", { method: "POST", body: { code, state: context }, client });
  } catch {
    return failed("kamaitachi");
  }
  if (upstream.ok) return redirect("/me/?kamaitachi=connected");
  const answer = (await upstream.json().catch(() => ({}))) as Record<string, unknown>;
  if (answer.error === "expired") return failed("kamaitachi_expired");
  if (answer.error === "rate_limited") return failed("rate_limited");
  return failed("kamaitachi");
}
