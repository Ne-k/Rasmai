import { env } from "./env";
import { oauthJson, revoke } from "./oauth";
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
  const tokens = await oauthJson<{ access_token?: string }>(`${DISCORD_API}/oauth2/token`, "token exchange", {
    form: {
      client_id: env.discordClientId(),
      client_secret: env.discordClientSecret(),
      grant_type: "authorization_code",
      code,
      redirect_uri: redirectUri(),
    },
  });
  const accessToken = String(tokens.access_token ?? "");
  if (!accessToken) throw new Error("token exchange returned no access token");

  const user = await oauthJson<{
    id: string;
    username?: string;
    global_name?: string | null;
    avatar?: string | null;
    email?: string | null;
    verified?: boolean;
  }>(`${DISCORD_API}/users/@me`, "identity read", { bearer: accessToken });

  revoke(`${DISCORD_API}/oauth2/token/revoke`, { client_id: env.discordClientId(), client_secret: env.discordClientSecret(), token: accessToken });

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
