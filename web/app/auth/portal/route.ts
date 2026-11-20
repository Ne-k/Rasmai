import { randomBytes } from "node:crypto";
import { env } from "@/lib/env";
import { redirect } from "@/lib/http";
import { cookieHeader, currentUser, readCookies, sign, verify } from "@/lib/session";
import { same, sessionCookie } from "@/lib/signin";

const ASKED_COOKIE = "rasmai_portal";
const ASKED_TTL = 300;
const NOTE_TTL = 60;

// Signing in to the developer portal. It has a host of its own (developers.<the site>) and so a session cookie of its own:
// the site's cookie stays on the site's host, and no other subdomain is ever sent it. Three steps, all here:
//   1. the portal's host gives this browser a one-time word in a cookie and sends it to the site with that word;
//   2. the site, if someone is signed in, signs a note good for a minute saying who, for that word, and sends it back;
//   3. the portal's host takes the note only from the browser holding the word, and turns it into its own session.
// The word is what makes a note no use to anyone else: a link carrying another person's note signs nobody in as them.
export async function GET(request: Request) {
  const query = new URL(request.url).searchParams;
  const site = new URL(env.publicUrl());
  if (!(request.headers.get("host") ?? "").startsWith("developers.")) {
    const user = currentUser(request);
    const asked = query.get("n") ?? "";
    if (!user || !/^[\w-]{24}$/.test(asked)) return redirect("/me/");
    // the person goes under "who", not at the top where a session keeps them: a note is then never taken for a session
    const note = sign({ who: user, aud: "portal", n: asked, exp: Date.now() / 1000 + NOTE_TTL });
    return redirect(`${site.protocol}//developers.${site.host}/auth/portal?t=${note}`);
  }
  if (!query.has("t")) {
    const asked = randomBytes(18).toString("base64url");
    const response = redirect(`${site.origin}/auth/portal?n=${asked}`);
    response.headers.append("Set-Cookie", cookieHeader(ASKED_COOKIE, asked, ASKED_TTL));
    return response;
  }
  const note = verify(query.get("t") ?? "");
  const asked = readCookies(request)[ASKED_COOKIE] ?? "";
  const response = redirect("/applications/");
  response.headers.append("Set-Cookie", cookieHeader(ASKED_COOKIE, "", 0));
  const who = (note?.who ?? {}) as Record<string, unknown>;
  if (note?.aud === "portal" && typeof who.id === "string" && asked && same(String(note.n ?? ""), asked)) {
    response.headers.append("Set-Cookie", sessionCookie({ id: who.id, name: String(who.name ?? ""), handle: String(who.handle ?? ""), avatar: String(who.avatar ?? "") }));
  }
  return response;
}
