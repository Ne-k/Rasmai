import { env } from "./env";
import type { PendingIdentity } from "./pending";

const DISCORD_API = "https://discord.com/api/v10";

const redirectUri = () => `${env.publicUrl()}/auth/callback`;

/** prompt=none skips Discord's consent screen for someone who already agreed. A person who signed in before the
 * email scope existed has not agreed to it, so Discord answers interaction_required and the caller asks again with
 * silent false. */
export function authorizeUrl(state: string, silent = true): string {
  const params = new URLSearchParams({
    client_id: env.discordClientId(),
    response_type: "code",
    scope: "identify email",
    redirect_uri: redirectUri(),
    state,
  });
  if (silent) params.set("prompt", "none");
  return `https://discord.com/oauth2/authorize?${params}`;
}

/** Trade the authorization code for the user's identity and email. Nothing else is asked for or kept. */
export async function exchangeCode(code: string): Promise<PendingIdentity> {
  const tokenResponse = await fetch(`${DISCORD_API}/oauth2/token`, {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body: new URLSearchParams({
      client_id: env.discordClientId(),
      client_secret: env.discordClientSecret(),
      grant_type: "authorization_code",
      code,
      redirect_uri: redirectUri(),
    }),
    signal: AbortSignal.timeout(15000),
    cache: "no-store",
  });
  if (!tokenResponse.ok) throw new Error(`token exchange failed: ${tokenResponse.status}`);
  const accessToken = String(((await tokenResponse.json()) as { access_token?: string }).access_token ?? "");
  if (!accessToken) throw new Error("token exchange returned no access token");

  const me = await fetch(`${DISCORD_API}/users/@me`, {
    headers: { Authorization: `Bearer ${accessToken}` },
    signal: AbortSignal.timeout(15000),
    cache: "no-store",
  });
  if (!me.ok) throw new Error(`identity read failed: ${me.status}`);
  const user = (await me.json()) as {
    id: string;
    username?: string;
    global_name?: string | null;
    avatar?: string | null;
    email?: string | null;
    verified?: boolean;
  };

  // the token has done its job; revoking it keeps nothing dangling on Discord's side
  fetch(`${DISCORD_API}/oauth2/token/revoke`, {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body: new URLSearchParams({ client_id: env.discordClientId(), client_secret: env.discordClientSecret(), token: accessToken }),
    signal: AbortSignal.timeout(10000),
  }).catch(() => undefined);

  const id = String(user.id);
  const avatar = user.avatar
    ? `https://cdn.discordapp.com/avatars/${id}/${user.avatar}.png?size=128`
    : `https://cdn.discordapp.com/embed/avatars/${Number((BigInt(id) >> 22n) % 6n)}.png`;
  const email = typeof user.email === "string" ? user.email.trim().slice(0, 254) : "";
  return {
    provider: "discord",
    subject: id,
    email,
    emailVerified: Boolean(email) && user.verified === true,
    name: (user.global_name || user.username || id).slice(0, 64),
    handle: (user.username ?? "").slice(0, 64),
    avatar,
  };
}
