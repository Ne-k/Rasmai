import { clientKey, json, parseBody } from "@/lib/http";
import { internal, passthrough } from "@/lib/internal";
import { apiLimiter } from "@/lib/limiter";

const FIELDS = ["client_id", "client_secret", "code_challenge", "code_challenge_method", "scope", "for"] as const;

const refused = (status: number, error: string, error_description: string) => json(status, { error, error_description });

// Where an app with no website starts a request for one player: the answer is the link to give them. It takes the client
// secret, so it is for a server to call: no other origin is let in to read the answer.
export async function POST(request: Request) {
  if (!apiLimiter.allow(clientKey(request))) return refused(429, "temporarily_unavailable", "Too many requests. Wait a minute.");
  let form: Record<string, string>;
  try {
    form = await parseBody(request);
  } catch {
    return refused(400, "invalid_request", "The body must be form-encoded or JSON.");
  }
  const body = Object.fromEntries(FIELDS.filter((field) => form[field]).map((field) => [field, form[field]]));
  try {
    const response = passthrough(await internal("/internal/oauth/link", { method: "POST", client: clientKey(request), body }));
    response.headers.set("Cache-Control", "no-store");
    return response;
  } catch {
    return refused(503, "temporarily_unavailable", "Rasmai can't answer right now.");
  }
}
