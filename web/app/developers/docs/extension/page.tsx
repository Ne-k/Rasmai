import type { Metadata } from "next";
import { Code, Table, places } from "../parts";

export const metadata: Metadata = { title: "Linking without OAuth" };

export default async function Extension() {
  const { site, base } = await places();
  return (
    <>
      <h1>Linking without OAuth</h1>
      <p className="dp-lede">
        The Aime sign-in helper can also hand a sign-in straight to your own site, with no Rasmai application. Four ways, least
        work first. The player always sees which host gets the sign-in before they press.
      </p>
      <p>
        The popup only looks at a page served over <code>https</code>, or over <code>http</code> on <code>localhost</code> while
        developing. Anywhere else it offers to copy.
      </p>
      <p>
        These suit a bot with its own link page. For anything else, <a href={`${base}/docs/`}>OAuth</a> is the better fit: the
        player never has to open the extension&apos;s popup.
      </p>

      <h2 id="nothing">0. Do nothing</h2>
      <p>
        On a page that declares nothing, the popup&apos;s button copies the cookie to the clipboard. If your site has a paste box,
        it already works.
      </p>

      <h2 id="input">1. Mark your input</h2>
      <p>The button types the cookie into it the way a person would, and the player presses your submit button.</p>
      <Code>{`<input name="clal">
<!-- or any name, with the attribute -->
<input name="token" data-aime-cookie>`}</Code>

      <h2 id="form">2. Declare a form</h2>
      <p>One press links. The extension posts the form to your own origin with the cookie added, then follows your redirect.</p>
      <Code>{`<form data-aime-link="token" action="/api/login" method="post" hidden>
  <input type="hidden" name="code" value="…">
</form>`}</Code>
      <p>
        The cookie is sent under the name in <code>data-aime-link</code>, as <code>application/x-www-form-urlencoded</code>. A
        form whose <code>action</code> is on another origin is refused.
      </p>

      <h2 id="link">3. Give out a link</h2>
      <p>
        The player pastes a link from your bot into the popup, from any tab. The link should hold an unguessable, short-lived,
        single-use code that says whose account to link: holding the link is the only proof.
      </p>
      <Code>{`GET  https://your.site/any/path/<code>
     200 { "aimeLink": 1, "ready": true }
     200 { "aimeLink": 1, "ready": false, "wait": "what to do first" }
     anything else is not a link; { "error": "words for the player" } is shown if present

POST https://your.site/any/path/<code>
     Content-Type: application/x-www-form-urlencoded
     clal=<64 letters and digits>

     200 { "ok": true, "player": "NAME" }
     otherwise { "ok": false, "error": "words for the player" }`}</Code>
      <Table
        label="Rules for a link"
        head={["Rule", "Why"]}
        rows={[
          [<>https only</>, <>Plain http is accepted for <code>localhost</code> and <code>127.0.0.1</code>, for developing.</>],
          [<>CORS</>, <>Every answer needs <code>Access-Control-Allow-Origin: *</code>. Both requests are simple ones, so there is no preflight.</>],
          [<>No cookies, no redirects</>, "The extension sends none of your site's cookies and does not follow redirects. Identify the player by the code in the link."],
          [<>Asked twice</>, <>The GET is asked again right before the POST, so <code>ready</code> can change while the popup is open.</>],
        ]}
      />
      <Code>{`@app.route("/aime/<code>", methods=["GET", "POST"])
def aime_link(code):
    who = pending_links.get(code)  # your own table of codes, with an expiry
    if who is None:
        body, status = {"error": "That link has expired. Ask the bot for a new one."}, 404
    elif request.method == "GET":
        body, status = {"aimeLink": 1, "ready": True}, 200
    else:
        clal = request.form.get("clal", "")
        if not re.fullmatch(r"[A-Za-z0-9]{64}", clal):
            body, status = {"ok": False, "error": "That is not an Aime sign-in."}, 400
        else:
            pending_links.pop(code)  # single use
            body, status = {"ok": True, "player": link_account(who, clal)}, 200
    return body, status, {"Access-Control-Allow-Origin": "*"}`}</Code>

      <h2 id="verified">Verified bots</h2>
      <p>
        The popup tells the player whether the site about to get their sign-in is a bot it knows. A verified bot is named with a
        tick. Any other site still works, but it is marked &quot;not a verified bot&quot; and the player has to press twice.
      </p>
      <p>
        A site proves it is verified with a grant: a short note signed by Rasmai that names the site&apos;s origin and runs out
        within a day. To be listed, ask Rasmai&apos;s developer.
      </p>
      <Code>{`GET ${site}/api/grant?origin=https://your.site
    200 { "ok": true, "grant": "<body>.<signature>", "name": "Your bot", "exp": 1790000000 }
    404 your origin is not listed`}</Code>
      <p>Fetch it from your server now and then (an hour&apos;s cache is plenty), then show it wherever the extension meets your site:</p>
      <ul>
        <li>
          on a page (ways 1 and 2): <code>data-aime-grant=&quot;&lt;grant&gt;&quot;</code> on the input, the form, or any element;
        </li>
        <li>
          on a link (way 3): <code>&quot;grant&quot;: &quot;&lt;grant&gt;&quot;</code> in the GET&apos;s answer, beside <code>&quot;aimeLink&quot;: 1</code>.
        </li>
      </ul>
    </>
  );
}
