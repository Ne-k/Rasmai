import type { Metadata } from "next";
import { Code, Table, places } from "../parts";

export const metadata: Metadata = { title: "OAuth2 reference" };

export default async function Reference() {
  const { site, base } = await places();
  return (
    <>
      <h1>OAuth2 reference</h1>
      <p className="dp-lede">The authorization code flow with PKCE. One scope, three endpoints.</p>

      <Table
        label="Endpoints"
        head={["Endpoint", "Address"]}
        rows={[
          [<>Authorize</>, <code key="a">{`${site}/oauth/authorize`}</code>],
          [<>Token</>, <code key="t">{`${site}/oauth/token`}</code>],
          [<>User info</>, <code key="u">{`${site}/oauth/userinfo`}</code>],
        ]}
      />

      <h2 id="authorize">Authorize</h2>
      <p>Send the player&apos;s browser here. Every parameter goes in the query string.</p>
      <Code>{`${site}/oauth/authorize?response_type=code&client_id=<client ID>&redirect_uri=<redirect>
    &scope=maimai:clal&state=<state>&code_challenge=<challenge>&code_challenge_method=S256`}</Code>
      <Table
        label="Authorize parameters"
        head={["Parameter", "Value"]}
        rows={[
          ["response_type", <><code>code</code></>],
          ["client_id", "Your application's client ID."],
          ["redirect_uri", <>One of the application&apos;s <a href="#redirects">redirects</a>, character for character.</>],
          ["scope", <><code>maimai:clal</code>. <code>openid</code> may be added and changes nothing.</>],
          ["state", "Anything up to 512 characters. It comes back unchanged, so you can check the answer belongs to your request."],
          ["code_challenge", <>From <a href="#pkce">PKCE</a>: 43 to 128 characters.</>],
          ["code_challenge_method", <><code>S256</code></>],
        ]}
      />
      <p>
        The page names your application and asks for the Aime sign-in helper if it is missing. The extension&apos;s window shows
        what Rasmai holds about your application, not what the page says: its name, picture, website, privacy policy, the host
        of the redirect, and your Discord handle (or &quot;a Google account&quot; if you signed in with Google). Rasmai does not
        review applications for now, so both the page and the window ask the player to continue only if they trust it. The request
        waits ten minutes for an answer.
      </p>
      <p>
        The player comes back to <code>redirect_uri</code> with <code>code</code> and <code>state</code>. If they decline,
        they come back with <code>error=access_denied</code> and <code>state</code>. If Rasmai cannot take a request, it shows
        the reason on its own page with a link back carrying <code>error</code>, <code>error_description</code> and{" "}
        <code>state</code>. Nothing reaches your redirect unless the player presses that link. <code>state</code> is left out when you
        sent none.
      </p>
      <Table
        label="Authorize errors"
        head={["Error", "When"]}
        rows={[
          ["access_denied", "The player declined. Sent to your redirect."],
          ["unsupported_response_type", <><code>response_type</code> is not <code>code</code>. Shown with a link back.</>],
          ["invalid_request", "No PKCE challenge, a method other than S256, or a state over 512 characters. Shown with a link back."],
          ["invalid_scope", <><code>maimai:clal</code> is missing, or there is a scope Rasmai does not have. Shown with a link back.</>],
          ["invalid_client", "No application has that client ID, or Rasmai has blocked it. Shown with no link back."],
          ["invalid_redirect", "The redirect is not one of the application's. Shown with no link back."],
          ["invalid_request", <>The redirect is the <a href="#no-website">done page</a>. Those requests start at <code>/oauth/link</code>. Shown with no link back.</>],
        ]}
      />

      <h2 id="redirects">Redirects</h2>
      <p>
        A redirect is an <code>https</code> address, or <code>http</code> on <code>localhost</code> or <code>127.0.0.1</code> while
        developing. It can be up to 200 characters with no <code>#</code> part. Custom schemes such as{" "}
        <code>myapp://callback</code> are not accepted. An application can have ten.
      </p>

      <h2 id="no-website">Apps with no website</h2>
      <p>
        A Discord bot, or anything else with no page to send the player back to, starts each request itself and asks Rasmai for
        the answer. No code is sent anywhere.
      </p>
      <ol>
        <li>
          On the application&apos;s OAuth2 page, make a client secret and add the done page to its redirects:{" "}
          <code>{`${site}/oauth/done`}</code>
        </li>
        <li>
          For each player, make a new <code>code_verifier</code> and start a request. <code>for</code> says who the link is
          for, in up to 40 characters, such as their Discord name. The player sees it before they approve.
        </li>
      </ol>
      <Code>{`POST ${site}/oauth/link
Content-Type: application/x-www-form-urlencoded

client_id=<client ID>&client_secret=<secret>&code_challenge=<challenge>&code_challenge_method=S256
  &for=<who the link is for>

200 { "link": "${site}/oauth/authorize?ticket=…", "expires_in": 600, "interval": 5 }`}</Code>
      <ol start={3}>
        <li>Give the player the link. It works for ten minutes and for one answer.</li>
        <li>
          Ask the token endpoint every five seconds with no <code>code</code>, until it answers or the ten minutes are up.
        </li>
      </ol>
      <Code>{`POST ${site}/oauth/token
Content-Type: application/x-www-form-urlencoded

grant_type=authorization_code&redirect_uri=${site}/oauth/done
  &client_id=<client ID>&client_secret=<secret>&code_verifier=<that player's verifier>`}</Code>
      <Table
        label="Answers while asking"
        head={["Answer", "When"]}
        rows={[
          [<>400 <code>authorization_pending</code></>, "The player has not answered yet. Ask again."],
          [<>400 <code>access_denied</code></>, "The player declined. Stop asking."],
          ["200", "The player approved. The body is the access token, as above."],
        ]}
      />
      <p>
        Never use one verifier for two players. Rasmai finds the answer by the verifier, so one player would get the other&apos;s
        sign-in. The token endpoint takes 1,200 requests a minute from one address, enough to ask about 100 players every five seconds. On a 429, wait.
      </p>
      <Table
        label="Link errors"
        head={["Error", "Status", "When"]}
        rows={[
          ["invalid_client", "401", "Unknown client ID, no client secret, or a wrong one."],
          ["unauthorized_client", "400", "The done page is not one of the application's redirects."],
          ["invalid_request", "400", <>No <code>for</code>, one over 40 characters, or no S256 challenge.</>],
          ["invalid_scope", "400", <><code>scope</code> was sent without <code>maimai:clal</code>.</>],
        ]}
      />

      <h2 id="pkce">PKCE</h2>
      <p>
        Every application needs it, with a secret or without. Make a random <code>code_verifier</code> of 43 to 128
        characters (letters, digits, <code>-</code> <code>.</code> <code>_</code> <code>~</code>) and keep it. The challenge is its
        SHA-256, as base64url with no padding.
      </p>
      <Code>{`const b64url = (bytes) => btoa(String.fromCharCode(...new Uint8Array(bytes)))
  .replace(/\\+/g, "-").replace(/\\//g, "_").replace(/=+$/, "");
const verifier = b64url(crypto.getRandomValues(new Uint8Array(32)));
const challenge = b64url(await crypto.subtle.digest("SHA-256", new TextEncoder().encode(verifier)));`}</Code>

      <h2 id="token">Token</h2>
      <p>Trade the code for an access token. The body is form-encoded or JSON.</p>
      <Code>{`POST ${site}/oauth/token
Content-Type: application/x-www-form-urlencoded

grant_type=authorization_code&code=<code>&redirect_uri=<the same redirect>
  &client_id=<client ID>&code_verifier=<verifier>`}</Code>
      <Table
        label="Token fields"
        head={["Field", "Value"]}
        rows={[
          ["grant_type", <><code>authorization_code</code></>],
          ["code", "The code from the redirect. It lasts five minutes and works once."],
          ["redirect_uri", "The redirect the code was sent to."],
          ["client_id", "Your client ID."],
          ["code_verifier", "The verifier the challenge was made from."],
          ["client_secret", <>Only if the application has one. <code>Authorization: Basic</code> with the ID and secret works too.</>],
        ]}
      />
      <Code>{`200 { "access_token": "…", "token_type": "Bearer", "expires_in": 3600, "scope": "maimai:clal" }`}</Code>
      <Table
        label="Token errors"
        head={["Error", "Status", "When"]}
        rows={[
          ["invalid_grant", "400", "The code is wrong, expired or already used, was issued for another client or redirect, or the verifier does not match."],
          ["invalid_client", "401", "Unknown client ID, or a missing or wrong secret."],
          ["invalid_request", "400", "The body is not form-encoded or JSON, or is over 64 KB."],
          ["unsupported_grant_type", "400", <><code>grant_type</code> is not <code>authorization_code</code>.</>],
          ["unauthorized_client", "400", <>The redirect is the <a href="#no-website">done page</a> and it is not one of the application&apos;s redirects.</>],
          ["temporarily_unavailable", "429, 503", "Too many requests, or Rasmai cannot answer right now."],
        ]}
      />
      <p>
        Rasmai refuses a code used a second time, and the token from its first use stops working too, since a code seen twice
        may have been stolen.
      </p>

      <h2 id="userinfo">User info</h2>
      <Code>{`GET ${site}/oauth/userinfo
Authorization: Bearer <access token>

200 { "sub": "…", "maimai_clal": "<64 letters and digits>", "maimai_clal_expires_at": 1790000000 }
401 { "error": "invalid_token" }`}</Code>
      <Table
        label="User info fields"
        head={["Field", "What it is"]}
        rows={[
          ["maimai_clal", <>The player&apos;s sign-in. See <a href={`${base}/docs/sign-in/`}>Using the sign-in</a>.</>],
          ["maimai_clal_expires_at", "When the sign-in runs out, in Unix seconds. 0 when not known."],
          ["sub", "A name for this player that only your application gets. It changes when the player signs in to maimai again, so do not use it as a permanent ID."],
        ]}
      />
      <p>
        The token lasts an hour and cannot be refreshed. Rasmai keeps the sign-in encrypted until then. After that it can no
        longer be read, and it is deleted within the hour. So read <code>userinfo</code> once and keep what you need. To get a
        newer sign-in, send the player through again.
      </p>

      <h2 id="clients">Secrets and browsers</h2>
      <p>
        A client secret is optional. Make one on the application&apos;s OAuth2 page if a server of yours does the token exchange;
        the token endpoint then refuses a request without it. Once made, a secret can be reset but not removed. An application
        with no server needs none: both the token and the user info endpoints answer requests from any origin.
      </p>
    </>
  );
}
