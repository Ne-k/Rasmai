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
    hint: "Sign out of the gateway, sign back in, then press the bookmark again. A Japan account links with its SEGA ID instead: run /login region:Japan in Discord.",
  },
  region: {
    headline: ["China accounts can't be linked ", "yet"],
    detail:
      "China's maimai DX NET only opens inside WeChat, and Rasmai has no way to sign in there yet, so this login can't finish however many times you try.",
    hint: "International and Japan accounts can be linked. If you also play on one of those, run /login in Discord and pick its region.",
  },
  credentials: {
    headline: ["maimaidx.jp said ", "no"],
    detail: "maimaidx.jp didn't accept that SEGA ID, password or Aime card.",
    hint: "Check them on maimaidx.jp, then try again. Your login link still works.",
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
