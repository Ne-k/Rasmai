import { clientKey, json, parseBody } from "@/lib/http";
import { internal, passthrough } from "@/lib/internal";
import { pollLimiter } from "@/lib/limiter";
import { open, preflight } from "@/lib/provider";

const FIELDS = ["grant_type", "code", "redirect_uri", "client_id", "code_verifier", "client_secret"] as const;

const refused = (status: number, error: string, error_description: string) => open(json(status, { error, error_description }));

/** The client id and secret from an `Authorization: Basic` header, the other standard place for them (RFC 6749 2.3.1). */
function basic(request: Request): Record<string, string> {
  const given = /^Basic +(\S+)$/i.exec(request.headers.get("authorization") ?? "");
  if (!given) return {};
  try {
    const [id, ...secret] = Buffer.from(given[1], "base64").toString("utf-8").split(":");
    return { client_id: decodeURIComponent(id), client_secret: decodeURIComponent(secret.join(":")) };
  } catch {
    return {};
  }
}

export function OPTIONS() {
  return preflight("POST, OPTIONS");
}

// The token endpoint: an app trades its code and PKCE verifier for an access token. The bot decides; errors are OAuth's own.
export async function POST(request: Request) {
  if (!pollLimiter.allow(clientKey(request))) return refused(429, "temporarily_unavailable", "Too many requests. Wait a minute.");
  let form: Record<string, string>;
  try {
    form = { ...basic(request), ...(await parseBody(request)) };
  } catch {
    return refused(400, "invalid_request", "The body must be form-encoded or JSON.");
  }
  const body = Object.fromEntries(FIELDS.filter((field) => form[field]).map((field) => [field, form[field]]));
  try {
    return open(passthrough(await internal("/internal/oauth/token", { method: "POST", client: clientKey(request), body })));
  } catch {
    return refused(503, "temporarily_unavailable", "Rasmai can't answer right now.");
  }
}
