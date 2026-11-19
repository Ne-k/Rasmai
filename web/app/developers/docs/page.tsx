import { Code, Table, places } from "./parts";

export default async function GettingStarted() {
  const { site, base } = await places();
  return (
    <>
      <h1>Getting started</h1>
      <p className="dp-lede">
        Rasmai is an OAuth 2.0 provider for one thing: a player&apos;s maimai DX sign-in. Your app sends the player to Rasmai, they
        approve it in the Aime sign-in helper extension, and your app gets the sign-in.
      </p>

      <h2 id="flow">How it goes</h2>
      <ol>
        <li>Your app sends the player to Rasmai&apos;s authorize page with your client ID.</li>
        <li>The page names your app. The player presses Continue, and the extension opens its own approval window.</li>
        <li>The player approves. The extension hands their sign-in to Rasmai, never to the page.</li>
        <li>Rasmai sends the player back to your redirect with a one-time code.</li>
        <li>Your app trades the code for an access token, then reads the sign-in with it.</li>
      </ol>
      <p>This is the authorization code flow with PKCE, like signing in with Discord or Google.</p>
      <p>
        The player needs the Aime sign-in helper, which runs in Chrome or Edge on a computer today. A Firefox version is in
        review. Safari, iPhone and Chrome on Android cannot run it.
      </p>

      <h2 id="quick-start">Quick start</h2>
      <ol>
        <li>
          <a href={`${base}/`}>Create an application</a>. It gets a client ID.
        </li>
        <li>
          On its OAuth2 page, add the redirect <code>http://localhost:8080/callback</code>.
        </li>
        <li>Serve the page below from that address, call <code>start()</code> from a button, and <code>finish()</code> on the callback.</li>
        <li>When you put it on a real site, add that site&apos;s <code>https</code> redirect too.</li>
      </ol>
      <p>
        No website, like a Discord bot? See <a href={`${base}/docs/oauth2/#no-website`}>Apps with no website</a>.
      </p>
      <p>
        The page below runs the whole flow in a browser so you can try it. In a real app, do the token exchange and{" "}
        <code>userinfo</code> on your server, so the sign-in never reaches a browser.
      </p>
      <Code>{`const CLIENT_ID = "<client ID>";
const REDIRECT = "http://localhost:8080/callback";
const AUTH = "${site}/oauth";
const b64url = (bytes) => btoa(String.fromCharCode(...new Uint8Array(bytes)))
  .replace(/\\+/g, "-").replace(/\\//g, "_").replace(/=+$/, "");

async function start() {
  const verifier = b64url(crypto.getRandomValues(new Uint8Array(32)));
  const challenge = b64url(await crypto.subtle.digest("SHA-256", new TextEncoder().encode(verifier)));
  const state = b64url(crypto.getRandomValues(new Uint8Array(16)));
  sessionStorage.setItem("oauth", JSON.stringify({ verifier, state }));
  location.href = \`\${AUTH}/authorize?\` + new URLSearchParams({
    response_type: "code", client_id: CLIENT_ID, redirect_uri: REDIRECT, scope: "maimai:clal",
    state, code_challenge: challenge, code_challenge_method: "S256",
  });
}

async function finish() {
  const query = new URLSearchParams(location.search);
  const { verifier, state } = JSON.parse(sessionStorage.getItem("oauth") ?? "{}");
  if (!query.get("code") || query.get("state") !== state) throw new Error(query.get("error") ?? "not this page's request");
  const token = await fetch(\`\${AUTH}/token\`, {
    method: "POST",
    body: new URLSearchParams({
      grant_type: "authorization_code", code: query.get("code"), redirect_uri: REDIRECT,
      client_id: CLIENT_ID, code_verifier: verifier,
    }),
  }).then((response) => response.json());
  if (!token.access_token) throw new Error(token.error_description ?? token.error);
  const answer = await fetch(\`\${AUTH}/userinfo\`, { headers: { Authorization: \`Bearer \${token.access_token}\` } });
  return answer.json(); // { sub, maimai_clal, maimai_clal_expires_at }
}`}</Code>

      <h2 id="limits">Limits</h2>
      <Table
        label="Limits"
        head={["What", "Limit"]}
        rows={[
          ["Applications", "10 for each developer"],
          ["Redirects", "10 for each application"],
          ["Authorization code", "5 minutes, used once"],
          ["Access token", "1 hour. There are no refresh tokens."],
          ["Requests", "240 a minute from one address"],
        ]}
      />
    </>
  );
}
