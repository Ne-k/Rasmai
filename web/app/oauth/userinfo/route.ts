import { clientKey, json } from "@/lib/http";
import { internal, passthrough } from "@/lib/internal";
import { apiLimiter } from "@/lib/limiter";
import { open, preflight } from "@/lib/provider";

const invalid = () => {
  const response = open(json(401, { error: "invalid_token" }));
  response.headers.set("WWW-Authenticate", 'Bearer error="invalid_token"');
  return response;
};

export function OPTIONS() {
  return preflight("GET, OPTIONS");
}

// What an access token is good for: the player's maimai sign-in, for the app that was approved.
export async function GET(request: Request) {
  if (!apiLimiter.allow(clientKey(request))) return open(json(429, { error: "temporarily_unavailable" }));
  const token = /^Bearer +(\S+)$/i.exec(request.headers.get("authorization") ?? "")?.[1];
  if (!token) return invalid();
  try {
    const upstream = await internal("/internal/oauth/userinfo", { method: "POST", body: { token } });
    return upstream.status === 401 ? invalid() : open(passthrough(upstream));
  } catch {
    return open(json(503, { error: "temporarily_unavailable" }));
  }
}
