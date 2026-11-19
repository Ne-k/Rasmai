import type { Metadata } from "next";
import { GATEWAY_HOST as GATEWAY, GATEWAY_LOGIN as LOGIN } from "@/lib/gateway";
import { Code, places } from "../parts";

export const metadata: Metadata = { title: "Using the sign-in" };

export default async function SignIn() {
  const { base } = await places();
  return (
    <>
      <h1>Using the sign-in</h1>
      <p className="dp-lede">
        <code>maimai_clal</code> is the player&apos;s <code>clal</code> cookie from SEGA&apos;s Aime gateway: 64 letters and digits that
        sign them in to maimai DX NET (International).
      </p>

      <h2 id="use">Signing in with it</h2>
      <ol>
        <li>
          Set it as the cookie <code>clal</code> on <code>{GATEWAY}</code>.
        </li>
        <li>
          GET the gateway&apos;s login address below, without following redirects. A 302 means the gateway accepted the sign-in; any
          other answer means it no longer works.
        </li>
        <li>
          GET the <code>Location</code> it answers with. The session you get back is signed in to <code>maimaidx-eng.com</code>.
        </li>
      </ol>
      <Code>{LOGIN}</Code>
      <Code>{`import requests

def maimai_session(clal: str) -> requests.Session:
    session = requests.Session()
    session.cookies.set("clal", clal, domain="${GATEWAY}")
    step = session.get("${LOGIN}", allow_redirects=False)
    if step.status_code != 302:
        raise RuntimeError("the sign-in no longer works: send the player through again")
    session.get(step.headers["Location"], allow_redirects=False)
    return session  # signed in to maimaidx-eng.com`}</Code>

      <h2 id="lasts">How long it lasts</h2>
      <p>
        Until <code>maimai_clal_expires_at</code>, or until the player signs out on the gateway, whichever comes first. When it
        stops working, send the player through <a href={`${base}/docs/oauth2/#authorize`}>authorize</a> again.
      </p>
      <p>
        The cookie only exists if the player ticked <b>auto login</b> when they signed in. Without it the extension finds no
        sign-in, and asks them to sign in again before they can approve.
      </p>

      <h2 id="care">Looking after it</h2>
      <p>It lets you act as the player on maimai DX NET, so treat it like a password.</p>
      <ul>
        <li>Keep it on your server, encrypted. Never send it to a browser or put it in a link.</li>
        <li>Keep it out of logs and error reports.</li>
        <li>Delete it when the player unlinks or deletes their account with you.</li>
        <li>Only read what your application says it reads. The player approved that and nothing else.</li>
      </ul>
    </>
  );
}
