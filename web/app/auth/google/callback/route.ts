import { clientKey, redirect } from "@/lib/http";
import { exchangeCode } from "@/lib/google";
import { oauthLimiter } from "@/lib/limiter";
import { back, finishSignIn, readFlow } from "@/lib/signin";

export async function GET(request: Request) {
  if (!oauthLimiter.allow(clientKey(request))) return redirect("/me/?error=rate_limited");
  const url = new URL(request.url);
  const flow = readFlow(request, "google", url.searchParams.get("state") ?? "");
  if (!flow || !flow.verifier) return back("state");
  if (url.searchParams.get("error")) return back("google");
  const code = url.searchParams.get("code") ?? "";
  if (!code) return back("state");

  let identity;
  try {
    identity = await exchangeCode(code, flow);
  } catch (error) {
    console.warn("Google sign-in failed:", error);
    return back("google");
  }
  return finishSignIn(request, flow, identity);
}
