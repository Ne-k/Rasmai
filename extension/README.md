# Aime sign-in helper

A browser extension for linking an International maimai DX account to a bot. SEGA made the Aime gateway's `clal` cookie
HttpOnly, so bookmarks and page scripts can no longer read it; an extension with the `cookies` permission still can. This one
reads it and hands it to the bot the person chooses, and to nothing else. It keeps nothing and has no server of its own.

It is not tied to any bot. Rasmai uses it, and any other bot can by doing one of the things below. Chrome, Edge and Firefox
(desktop and Android) work; Safari does not let extensions read HttpOnly cookies, so there is no Safari or iPhone build.

## For bot developers: four ways in, least work first

Pick whichever fits your site. The person always sees which host gets the sign-in before they press.

### 0. Do nothing

On a page that declares nothing, the button copies the cookie to the clipboard, and a second "Copy" button does the same
from any tab. If your site has a paste box, it already works.

### 1. Mark your input: the button fills it

```html
<input name="clal">                      <!-- or any name, with the attribute: -->
<input name="token" data-aime-cookie>
```

The value is typed in the way a person would type it (React and other frameworks notice), and the person presses your submit.

### 2. Declare a form: one press links

```html
<form data-aime-link="token" action="/api/login" method="post" hidden>
  <input type="hidden" name="code" value="…">       <!-- whatever your endpoint needs to know who this is -->
</form>
```

The extension posts that form (`application/x-www-form-urlencoded`) to your own origin with the cookie added under the name
in `data-aime-link`, then follows your redirect in the page, so answer with a redirect to your "linked" page. A form whose
`action` is on another origin is refused.

### 3. Give out a link: no page of yours has to be open

The person pastes a link from your bot into the extension, from any tab. Your bot makes the link; it should hold an
unguessable, short-lived, single-use code that says whose account to link, because holding the link is the only proof.

```
GET  https://your.site/any/path/<code>
     200 { "aimeLink": 1, "ready": true }
     not ready yet (say, a check to pass first): { "aimeLink": 1, "ready": false, "wait": "what to do" }
     anything else, or no "aimeLink": 1: not a link. { "error": "words for the person" } is shown if present.

POST https://your.site/any/path/<code>      Content-Type: application/x-www-form-urlencoded      body: clal=<64 letters and digits>
     200 { "ok": true, "player": "NAME" }           player is optional
     otherwise { "ok": false, "error": "words for the person" }
```

Rules the extension holds you to:

- `https` only (plain `http` is accepted for `localhost` and `127.0.0.1`, for developing).
- Every answer needs `Access-Control-Allow-Origin: *`. Both requests are "simple" ones, so there is no preflight to answer.
- Redirects are not followed and none of your site's cookies are sent: identify the person by the code in the link.
- The GET is asked again right before the POST, so `ready` can change while the popup is open.

A whole endpoint, in Flask:

```python
@app.route("/aime/<code>", methods=["GET", "POST"])
def aime_link(code):
    who = pending_links.get(code)                      # your own table of codes you gave out, with an expiry
    if who is None:
        body, status = {"error": "That link has expired. Ask the bot for a new one."}, 404
    elif request.method == "GET":
        body, status = {"aimeLink": 1, "ready": True}, 200
    else:
        clal = request.form.get("clal", "")
        if not re.fullmatch(r"[A-Za-z0-9]{64}", clal):
            body, status = {"ok": False, "error": "That is not an Aime sign-in."}, 400
        else:
            pending_links.pop(code)                    # single use
            player = link_account(who, clal)           # sign in to maimai DX NET with it and store it encrypted
            body, status = {"ok": True, "player": player}, 200
    return body, status, {"Access-Control-Allow-Origin": "*"}
```

Rasmai's own is `web/app/api/link/[key]/route.ts`.

To use the cookie: set it as `clal` on `lng-tgk-aime-gw.am-all.net`, GET
`https://lng-tgk-aime-gw.am-all.net/common_auth/login?site_id=maimaidxex&redirect_url=https://maimaidx-eng.com/maimai-mobile/&back_url=https://maimai.sega.com/`
without following redirects, then GET the `Location` it answers with. That session is signed in to maimaidx-eng.com.

## Trying it

- Chrome, Edge: `chrome://extensions` → Developer mode → Load unpacked → this folder.
- Firefox: `about:debugging#/runtime/this-firefox` → Load Temporary Add-on → `manifest.json` here. Firefox asks for the gateway
  permission the first time the button is pressed.

`node extension/test/run.mjs` loads it into a throwaway headless Google Chrome, sets the cookie as SEGA sets it (HttpOnly) and
presses the button against stand-ins for each of the four ways, the link endpoint on an origin the extension holds no
permission for. The real extension reaches a page through `activeTab`, which only a real press grants, so the test copy is
given the local pages' host instead.

## Publishing

- Chrome Web Store: a developer account (one-time fee) and a review; Edge Add-ons takes the same zip for free.
- Firefox: addons.mozilla.org signs it for free; the `gecko.id` in `manifest.json` is the add-on's identity there, and the
  `data_collection_permissions` entry is the declaration it requires.

The icon is the extension's own: a card with tap waves, drawn at 16, 48 and 128 pixels.
