export type ErrorCopy = { headline: [string, string]; detail: string; hint: string };

export const ERROR_COPY: Record<string, ErrorCopy> = {
  expired: {
    headline: ["That link has ", "expired"],
    detail: "Login links work once and last about ten minutes.",
    hint: "Run /login in Discord again for a fresh link.",
  },
  invalid_user: {
    headline: ["This link isn't ", "valid"],
    detail: "It's missing your Discord account info, or it was changed.",
    hint: "Run /login in Discord and use the link it gives you as-is.",
  },
  maintenance: {
    headline: ["maimai DX NET is ", "down"],
    detail: "Your Aime sign-in worked, but the maimai DX NET score site is down right now, so your session can't be checked yet.",
    hint: "Your login link still works. Press the bookmark again once the servers are back. The bar at the top shows when.",
  },
  no_login: {
    headline: ["Couldn't read your ", "session"],
    detail: "You may not be signed in to the SEGA gateway yet, or the sign-in didn't stick.",
    hint: "Sign out of the gateway, sign back in, then press the bookmark again. Japan and China accounts can't be linked yet.",
  },
  region: {
    headline: ["Only International accounts ", "for now"],
    detail:
      "Rasmai signs in through SEGA's international Aime gateway. Japan accounts sign in with SEGA ID on maimaidx.jp and China accounts with WeChat, so this login can't finish, and signing out and in again won't change that.",
    hint: "Support for more regions is planned. If you also play on an International account, run /login in Discord without a region.",
  },
  rate_limited: {
    headline: ["Too many ", "attempts"],
    detail: "Sign-in attempts from your connection are paused for a few minutes.",
    hint: "Wait ten minutes, then run /login in Discord for a fresh link.",
  },
  upstream: {
    headline: ["maimai said ", "no"],
    detail: "The sign-in was read correctly, but the maimai site rejected it.",
    hint: "The session probably expired partway through. Your login link still works, so sign in to the gateway again and press the bookmark.",
  },
  verify: {
    headline: ["One check was ", "skipped"],
    detail: "You need to pass the human check on the connect page before signing in.",
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
