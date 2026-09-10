export type ErrorCopy = { headline: [string, string]; detail: string; hint: string };

export const ERROR_COPY: Record<string, ErrorCopy> = {
  expired: {
    headline: ["That link has ", "expired"],
    detail: "Login links work once and last about ten minutes.",
    hint: "Run /login in Discord again for a fresh link.",
  },
  invalid_user: {
    headline: ["This link isn't ", "valid"],
    detail: "It's missing the part that identifies your Discord account, or it was altered.",
    hint: "Run /login in Discord and use the link it gives you, unchanged.",
  },
  maintenance: {
    headline: ["maimai DX NET is ", "down"],
    detail:
      "Your Aime sign-in worked, but that gateway and the maimai DX NET score site are two different things, and the score site is the one your session has to be checked against. It is in maintenance or not answering, so the check cannot happen yet.",
    hint: "Nothing was used up: your login link still works. Press the bookmark again once the servers are back. The band at the top says when.",
  },
  no_login: {
    headline: ["Couldn't read your ", "session"],
    detail: "You may not be signed in to the SEGA gateway yet, or the sign-in didn't stick.",
    hint: "Sign out of the gateway, sign back in, then press the bookmark again.",
  },
  rate_limited: {
    headline: ["Too many ", "attempts"],
    detail: "Sign-in attempts from your connection are paused for a few minutes.",
    hint: "Wait ten minutes, then run /login in Discord for a fresh link.",
  },
  upstream: {
    headline: ["maimai said ", "no"],
    detail: "The sign-in was read correctly, but the maimai site rejected it.",
    hint: "That usually means the session expired mid-way. Your login link is still good: sign in to the gateway again, then press the bookmark.",
  },
  verify: {
    headline: ["One check was ", "skipped"],
    detail: "The bot needs the quick human check on the connect page before it accepts a sign-in.",
    hint: "Go back to the connect page, pass the check, then press the bookmark again.",
  },
  unknown: {
    headline: ["Something went ", "wrong"],
    detail: "The connection couldn't be completed.",
    hint: "Run /login in Discord to start over.",
  },
};

export function errorCopy(kind: string | null | undefined): ErrorCopy {
  return ERROR_COPY[kind ?? ""] ?? ERROR_COPY.unknown;
}
