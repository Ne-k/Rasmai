import { createHash } from "node:crypto";
import { env } from "./env";
import type { PendingIdentity } from "./pending";

const redirectUri = () => `${env.publicUrl()}/auth/google/callback/`;

type Secrets = { state: string; verifier: string; nonce: string };

export function authorizeUrl({ state, verifier, nonce }: Secrets): string {
  const params = new URLSearchParams({
    client_id: env.googleClientId(),
    response_type: "code",
    scope: "openid email profile",
    redirect_uri: redirectUri(),
    state,
    nonce,
    code_challenge: createHash("sha256").update(verifier).digest("base64url"),
    code_challenge_method: "S256",
    prompt: "select_account",
  });
  return `https://accounts.google.com/o/oauth2/v2/auth?${params}`;
}

/** What the ID token says without checking its signature: it came straight from Google's token endpoint over TLS,
 * which is the case the OpenID spec allows that for. It is only used to tie the answer to this sign-in. */
function claims(idToken: string): Record<string, unknown> {
  try {
    return JSON.parse(Buffer.from(idToken.split(".")[1] ?? "", "base64url").toString("utf-8")) as Record<string, unknown>;
  } catch {
    return {};
  }
}

/** Trade the authorization code for who signed in: Google's stable id, name and email. No avatar is read or kept. */
export async function exchangeCode(code: string, { verifier, nonce }: Secrets): Promise<PendingIdentity> {
  const tokenResponse = await fetch("https://oauth2.googleapis.com/token", {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body: new URLSearchParams({
      client_id: env.googleClientId(),
      client_secret: env.googleClientSecret(),
      grant_type: "authorization_code",
      code,
      code_verifier: verifier,
      redirect_uri: redirectUri(),
    }),
    signal: AbortSignal.timeout(15000),
    cache: "no-store",
  });
  if (!tokenResponse.ok) throw new Error(`token exchange failed: ${tokenResponse.status}`);
  const tokens = (await tokenResponse.json()) as { access_token?: string; id_token?: string };
  const accessToken = String(tokens.access_token ?? "");
  if (!accessToken) throw new Error("token exchange returned no access token");

  const token = claims(String(tokens.id_token ?? ""));
  const issuer = String(token.iss ?? "");
  if (issuer !== "https://accounts.google.com" && issuer !== "accounts.google.com") throw new Error("id token has the wrong issuer");
  if (token.aud !== env.googleClientId()) throw new Error("id token is for another client");
  if (token.nonce !== nonce) throw new Error("id token nonce does not match");

  const response = await fetch("https://openidconnect.googleapis.com/v1/userinfo", {
    headers: { Authorization: `Bearer ${accessToken}` },
    signal: AbortSignal.timeout(15000),
    cache: "no-store",
  });
  if (!response.ok) throw new Error(`identity read failed: ${response.status}`);
  const info = (await response.json()) as { sub?: string; email?: string; email_verified?: boolean | string; name?: string; given_name?: string };

  // the token has done its job; revoking it keeps nothing dangling on Google's side
  fetch("https://oauth2.googleapis.com/revoke", {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body: new URLSearchParams({ token: accessToken }),
    signal: AbortSignal.timeout(10000),
  }).catch(() => undefined);

  const subject = String(info.sub ?? "");
  if (!subject || subject !== token.sub) throw new Error("userinfo does not match the id token");
  const email = typeof info.email === "string" ? info.email.trim().slice(0, 254) : "";
  return {
    provider: "google",
    subject,
    email,
    // exactly what Google says: an address Google has not verified never counts as proof of who someone is
    emailVerified: Boolean(email) && (info.email_verified === true || info.email_verified === "true"),
    name: String(info.name || info.given_name || "Google user").slice(0, 64),
    handle: "",
    avatar: "",
  };
}
