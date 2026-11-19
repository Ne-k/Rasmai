import { spawn } from "node:child_process";
import { createHash, generateKeyPairSync, sign } from "node:crypto";
import { cpSync, mkdtempSync, readFileSync, writeFileSync } from "node:fs";
import { createServer } from "node:http";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

// node extension/test/run.mjs (needs Google Chrome and the network)

const HERE = dirname(fileURLToPath(import.meta.url));
const SOURCE = join(HERE, "..");
const CHROME = process.env.CHROME ?? "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe";
const PORT = 3000;
const SITE = `http://localhost:${PORT}`;
const GATEWAY_PAGE = "https://lng-tgk-aime-gw.am-all.net/common_auth/";

const page = readFileSync(join(HERE, "connect.html"), "utf8");
const { publicKey, privateKey } = generateKeyPairSync("ed25519");
const b64 = (data) => Buffer.from(data).toString("base64url");
const grant = (origin, seconds = 3600) => {
  const body = b64(JSON.stringify({ v: 1, name: "Test bot", origin, exp: Math.floor(Date.now() / 1000) + seconds }));
  return `${body}.${b64(sign(null, Buffer.from(`aime-grant.${body}`), privateKey))}`;
};
// what rasmai.lol signs for the approval window: the request, naming its ticket
const signedRequest = (ticket, key = privateKey, icon = "", reviews, who, where = new URL(SITE).host) => {
  const asked = { app: { name: "Test <i>app</i>", by: "Someone", website: "https://app.example/", privacy: "", verified: false, icon }, redirectHost: where, scopes: ["maimai:clal"], ...(reviews === undefined ? {} : { reviews }), ...(who ? { for: who } : {}) };
  const body = b64(JSON.stringify({ v: 1, ticket, exp: Math.floor(Date.now() / 1000) + 600, ...asked }));
  return { ok: true, ...asked, signed: `${body}.${b64(sign(null, Buffer.from(`aime-oauth.${body}`), key))}` };
};
// an app's picture, and the two requests that name it: one by the mark of these bytes, one by the mark of some other picture
const PNG = Buffer.from("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==", "base64");
const pictured = (mark) => `/api/oauth/icon/${"a".repeat(24)}?v=${mark}`;
const ICONS = { shown: ["i".repeat(32), pictured(createHash("sha256").update(PNG).digest("hex").slice(0, 32))], swapped: ["j".repeat(32), pictured("0".repeat(32))] };
const UNREVIEWING = "r".repeat(32);
const LABELLED = "l".repeat(32);
const ELSEWHERE = "e".repeat(32);
const FORGED = { unsigned: "u".repeat(32), stranger: "w".repeat(32), swapped: "x".repeat(32), asgrant: "y".repeat(32) };
const without = (html, part) => html.replace(new RegExp(`<!--${part}-->[\\s\\S]*?<!--/${part}-->`), "");
const posted = [];
const TICKET = "t".repeat(32);
const decided = [];
const server = createServer((request, response) => {
  if (request.method === "POST" && request.url === "/api/login") {
    let body = "";
    request.on("data", (chunk) => { body += chunk; });
    request.on("end", () => {
      posted.push(Object.fromEntries(new URLSearchParams(body)));
      response.writeHead(303, { Location: "/connected/?player=test" });
      response.end();
    });
    return;
  }
  // rasmai.lol's part of an approval: what a ticket asks for, and where approving or declining it sends the player
  const json = (status, body) => { response.writeHead(status, { "Content-Type": "application/json", "Access-Control-Allow-Origin": "*" }); response.end(JSON.stringify(body)); };
  const decision = request.method === "POST" && /^\/api\/oauth\/(approve|deny)$/.exec(request.url)?.[1];
  if (decision) {
    let body = "";
    request.on("data", (chunk) => { body += chunk; });
    request.on("end", () => {
      const sent = Object.fromEntries(new URLSearchParams(body));
      decided.push([decision, sent]);
      const redirect = `${SITE}/connected/?${decision === "approve" ? "code=c1" : "error=access_denied"}&state=s1`;
      setTimeout(() => ([TICKET, ELSEWHERE].includes(sent.ticket) ? json(200, { ok: true, redirect }) : json(400, { ok: false, error: "expired" })), decision === "approve" ? 800 : 0);
    });
    return;
  }
  if (request.url.startsWith("/api/oauth/icon/")) {
    response.writeHead(200, { "Content-Type": "image/png", "Access-Control-Allow-Origin": "*" });
    return response.end(PNG);
  }
  if (request.url.startsWith("/api/oauth/request/")) {
    const asked = request.url.split("/").pop();
    if (asked === TICKET) return json(200, signedRequest(TICKET));
    if (asked === UNREVIEWING) return json(200, signedRequest(asked, privateKey, "", false));
    if (asked === ELSEWHERE) return json(200, signedRequest(asked, privateKey, "", undefined, undefined, "app.example"));
    if (asked === LABELLED) return json(200, signedRequest(asked, privateKey, "", false, "nek_ng on Discord"));
    for (const [ticket, icon] of Object.values(ICONS)) if (asked === ticket) return json(200, signedRequest(ticket, privateKey, icon));
    // every way an answer can fail to be rasmai.lol's: no signature, someone else's key, another ticket's signature, a grant's
    if (asked === FORGED.unsigned) return json(200, { ...signedRequest(asked), signed: undefined });
    if (asked === FORGED.stranger) return json(200, signedRequest(asked, generateKeyPairSync("ed25519").privateKey));
    if (asked === FORGED.swapped) return json(200, signedRequest(TICKET));
    if (asked === FORGED.asgrant) return json(200, { ...signedRequest(asked), signed: grant(SITE) });
    return json(404, { ok: false, error: "expired" });
  }
  // the consent page's part, as rasmai.lol/oauth/authorize draws it: a button carrying the ticket
  const asks = (ticket) => `<!doctype html><meta charset="utf-8"><button id="yes" data-aime-oauth data-aime-ticket="${ticket}">Continue with extension</button>`;
  const html = request.url.startsWith("/oauth/authorize") || request.url.startsWith("/elsewhere/") ? asks(request.url.includes("gone") ? "g".repeat(32) : FORGED[new URL(request.url, SITE).searchParams.get("forged")] ?? ICONS[new URL(request.url, SITE).searchParams.get("icon")]?.[0] ?? (request.url.includes("reviews=off") ? UNREVIEWING : request.url.includes("who=") ? LABELLED : request.url.includes("where=") ? ELSEWHERE : TICKET))
    : request.url.startsWith("/connect/") ? page : request.url.startsWith("/field/") ? without(page, "FORM")
    : request.url.startsWith("/connected/") ? "<h1 id='linked'>linked</h1>" : without(without(page, "FORM"), "FIELD");
  response.writeHead(200, { "Content-Type": "text/html" });
  response.end(html.replaceAll("__GRANT__", request.url.includes("unlisted") ? "" : grant(SITE)));
}).listen(PORT, "127.0.0.1");

const LINKS = `http://localhost:${PORT + 1}`;
const linked = [];
const links = createServer((request, response) => {
  const answer = (status, body) => { response.writeHead(status, { "Content-Type": "application/json", "Access-Control-Allow-Origin": "*" }); response.end(JSON.stringify(body)); };
  if (request.url === "/not-a-link") return answer(200, { hello: "world" });
  if (request.url === "/link/waiting") return answer(200, { aimeLink: 1, grant: grant(LINKS), ready: false, wait: "Pass the check first." });
  if (request.url === "/link/borrowed" || request.url === "/link/stale") return answer(200, { aimeLink: 1, grant: request.url === "/link/stale" ? grant(LINKS, -60) : grant(SITE), ready: true });
  if (request.url === "/link/slow") {
    if (request.method === "GET") return answer(200, { aimeLink: 1, grant: grant(LINKS), ready: true });
    request.resume();
    return request.on("end", () => setTimeout(() => answer(200, { ok: true, player: "SLOW" }), 1500));
  }
  if (request.url !== "/link/abc" && request.url !== "/link/stranger") return answer(404, { error: "That link has expired." });
  if (request.method === "GET") return answer(200, { aimeLink: 1, grant: request.url === "/link/abc" ? grant(LINKS) : undefined, ready: true });
  let body = "";
  request.on("data", (chunk) => { body += chunk; });
  request.on("end", () => { linked.push(Object.fromEntries(new URLSearchParams(body))); answer(200, { ok: true, player: "TEST" }); });
}).listen(PORT + 1, "127.0.0.1");

const work = mkdtempSync(join(tmpdir(), "aime-helper-"));
const copy = join(work, "extension");
cpSync(SOURCE, copy, { recursive: true, filter: (path) => !path.startsWith(HERE) });
const manifest = JSON.parse(readFileSync(join(copy, "manifest.json"), "utf8"));
manifest.host_permissions.push(`${SITE}/*`, `http://plain.test:${PORT}/*`);
manifest.content_scripts[0].matches = [`${SITE}/oauth/authorize*`];
delete manifest.browser_specific_settings;
writeFileSync(join(copy, "manifest.json"), JSON.stringify(manifest));
const script = readFileSync(join(copy, "core.js"), "utf8");
if (!script.includes("const GRANT_KEYS = [") || !script.includes('const HOME = "https://rasmai.lol";')) throw new Error("core.js no longer holds its grant keys and home where the test puts its own");
writeFileSync(join(copy, "core.js"), script.replace(/const GRANT_KEYS = \[.*?\];/s, `const GRANT_KEYS = ["not a key", ${JSON.stringify(publicKey.export({ format: "jwk" }).x)}];`)
  .replace('const HOME = "https://rasmai.lol";', `const HOME = ${JSON.stringify(SITE)};`));

const chrome = spawn(CHROME, [
  "--headless=new", "--remote-debugging-pipe", "--enable-unsafe-extension-debugging", "--host-resolver-rules=MAP plain.test 127.0.0.1",
  `--user-data-dir=${join(work, "profile")}`, "--no-first-run", "--no-default-browser-check", "--window-size=1200,900", "about:blank",
], { stdio: ["ignore", "ignore", "pipe", "pipe", "pipe"] });
chrome.stderr.on("data", (d) => { const s = String(d); if (/manifest/i.test(s)) process.stderr.write("[chrome] " + s); });

let nextId = 1;
const waiting = new Map();
let buffer = "";
chrome.stdio[4].on("data", (chunk) => {
  buffer += chunk.toString();
  let at;
  while ((at = buffer.indexOf("\0")) >= 0) {
    const message = JSON.parse(buffer.slice(0, at));
    buffer = buffer.slice(at + 1);
    if (message.id && waiting.has(message.id)) {
      const { resolve, reject } = waiting.get(message.id);
      waiting.delete(message.id);
      message.error ? reject(new Error(`${message.error.message} (${message.error.data ?? ""})`)) : resolve(message.result);
    }
  }
});
function send(method, params = {}, sessionId) {
  const id = nextId++;
  chrome.stdio[3].write(JSON.stringify({ id, method, params, sessionId }) + "\0");
  return new Promise((resolve, reject) => waiting.set(id, { resolve, reject }));
}
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
async function until(read, done, limit = 8000) {
  const started = Date.now();
  for (;;) {
    const value = await read();
    if (done(value) || Date.now() - started > limit) return value;
    await sleep(100);
  }
}

async function open(url) {
  const { targetId } = await send("Target.createTarget", { url });
  const { sessionId } = await send("Target.attachToTarget", { targetId, flatten: true });
  await send("Runtime.enable", {}, sessionId);
  return { targetId, sessionId };
}
async function evaluate(sessionId, expression) {
  const { result, exceptionDetails } = await send("Runtime.evaluate", { expression, awaitPromise: true, returnByValue: true }, sessionId);
  if (exceptionDetails) throw new Error(exceptionDetails.exception?.description ?? exceptionDetails.text);
  return result.value;
}

const failures = [];
const expect = (name, got, want) => {
  const ok = JSON.stringify(got) === JSON.stringify(want);
  console.log(`${ok ? "ok  " : "FAIL"}  ${name}${ok ? "" : `: got ${JSON.stringify(got)}, wanted ${JSON.stringify(want)}`}`);
  if (!ok) failures.push(name);
};

try {
  const { id } = await send("Extensions.loadUnpacked", { path: copy });
  expect("Chrome loads the extension", typeof id, "string");
  await send("Browser.grantPermissions", { origin: `chrome-extension://${id}`, permissions: ["clipboardReadWrite", "clipboardSanitizedWrite"] });

  const popupOn = async (targetId) => {
    await send("Target.activateTarget", { targetId });
    const action = await open(`chrome-extension://${id}/popup.html`);
    await send("Target.activateTarget", { targetId });
    const label = () => evaluate(action.sessionId, "(document.getElementById('go')?.textContent ?? '…') + ' | ' + (document.getElementById('dest')?.textContent ?? '')");
    const said = () => evaluate(action.sessionId, "document.getElementById('said').textContent");
    const who = () => evaluate(action.sessionId, "document.getElementById('who').textContent");
    await until(label, (text) => !text.startsWith("…"));
    return {
      ...action,
      label,
      who,
      card: () => evaluate(action.sessionId, "document.getElementById('card').dataset.state + ' / ' + document.getElementById('until').textContent"),
      press: async (wait = true, which = "go") => {
        await evaluate(action.sessionId, "document.getElementById('said').textContent = ''");
        const { x, y } = await evaluate(action.sessionId, `(({ x, y, width, height }) => ({ x: x + width / 2, y: y + height / 2 }))(document.getElementById('${which}').getBoundingClientRect())`);
        for (const type of ["mousePressed", "mouseReleased"]) {
          await send("Input.dispatchMouseEvent", { type, x, y, button: "left", clickCount: 1 }, action.sessionId);
        }
        return wait ? until(said, (text) => text !== "") : "";
      },
    };
  };

  const loaded = async (session) => {
    const ready = await until(() => evaluate(session, "document.readyState === 'complete' && (!document.getElementById('root') || !!document.getElementById('state'))"), Boolean);
    if (!ready) throw new Error("the stand-in page's React field never appeared: React is loaded from a CDN, so this test needs the network");
  };
  const connect = await open(`${SITE}/connect/?code=test&user=someone`);
  await loaded(connect.sessionId);
  let popup = await popupOn(connect.targetId);
  expect("a page with a declared form gets the link button, naming the host", await popup.label(), "Link my account | localhost:3000");
  expect("a page carrying a grant signed for it is named as the verified bot", await popup.who(), "✓ Test bot");
  expect("the card says nobody is signed in", await popup.card(), "none / Sign in on the maimai site");
  expect("without a cookie the popup says to sign in", await popup.press(), "Not signed in. Sign in");
  expect("and posts nothing", posted.length, 0);

  // the consent page: a real press on its button has the extension open its own approval window
  const really = async (session, element) => {
    const { x, y } = await evaluate(session, `(({ x, y, width, height }) => ({ x: x + width / 2, y: y + height / 2 }))(document.getElementById('${element}').getBoundingClientRect())`);
    for (const type of ["mousePressed", "mouseReleased"]) await send("Input.dispatchMouseEvent", { type, x, y, button: "left", clickCount: 1 }, session);
  };
  const asking = async (path) => {
    const tab = await open(`${SITE}${path}`);
    await until(() => evaluate(tab.sessionId, "location.protocol === 'http:' && document.readyState === 'complete'"), Boolean);
    await send("Target.activateTarget", { targetId: tab.targetId });
    await evaluate(tab.sessionId, "document.addEventListener('aime-opened', (event) => { document.title = 'heard from ' + event.target.id; })");
    return tab;
  };
  const marked = (session) => evaluate(session, "document.getElementById('yes').hasAttribute('data-aime-opened')");
  const windows = async () => (await send("Target.getTargets")).targetInfos.filter((target) => target.url.startsWith(`chrome-extension://${id}/approve.html`));
  const gone = async () => (await until(windows, (all) => all.length === 0, 4000)).length === 0;
  const approval = async (tab) => {
    await really(tab.sessionId, "yes");
    const [found] = await until(windows, (all) => all.length > 0, 4000);
    if (!found) throw new Error("the approval window never opened");
    const { sessionId } = await send("Target.attachToTarget", { targetId: found.targetId, flatten: true });
    await send("Runtime.enable", {}, sessionId);
    const said = () => evaluate(sessionId, "document.getElementById('said')?.textContent ?? ''");
    await until(() => evaluate(sessionId, "document.getElementById('ask')?.hidden === false || !!document.getElementById('said')?.textContent"), Boolean);
    return {
      sessionId,
      said,
      close: async () => { await send("Target.closeTarget", { targetId: found.targetId }); return gone(); },
      press: async (which, wait = true) => { await really(sessionId, which); return wait ? until(said, (text) => text !== "") : ""; },
    };
  };
  let consent = await asking("/oauth/authorize?client_id=test");
  expect("the consent page is told the extension is there, and its version", await evaluate(consent.sessionId, "document.documentElement.getAttribute('data-aime-helper')"), manifest.version);
  await evaluate(consent.sessionId, "document.getElementById('yes').click()");
  await sleep(700);
  expect("a press made by the page's own script is not a press: no window opens", [(await windows()).length, await marked(consent.sessionId)], [0, false]);
  let approving = await approval(consent);
  expect("a real press opens the approval window, and the page is told so on its button",
    [await until(() => marked(consent.sessionId), Boolean, 2000), await evaluate(consent.sessionId, "document.title")], [true, "heard from yes"]);
  expect("the window shows the app as rasmai.lol describes it, where it sends the player, and that nobody reviewed it",
    await evaluate(approving.sessionId, "['title', 'app', 'by', 'dest', 'badge'].map((id) => document.getElementById(id).textContent).concat(document.getElementById('unreviewed').hidden)"),
    ["Test <i>app</i> wants your maimai sign-in", "Test <i>app</i>", "Someone", new URL(SITE).host, "not reviewed", false]);
  expect("the app's name is shown as text, its website opens in a new tab, and a row with nothing to say is left out",
    await evaluate(approving.sessionId, "(() => { const a = document.querySelector('#website a'); return [document.querySelector('#ask i') === null, a.href, a.target, document.getElementById('privacy').parentNode.hidden]; })()"),
    [true, "https://app.example/", "_blank", true]);
  expect("with nobody signed in, Approve says so and sends nothing", [await approving.press("go"), decided.length], ["Not signed in. Sign in", 0]);
  expect("and the window is still there to close", await approving.close(), true);

  consent = await asking("/oauth/authorize?client_id=test");
  await really(consent.sessionId, "yes");
  await really(consent.sessionId, "yes");
  await sleep(1200);
  const twice = await windows();
  expect("two presses in a row open one window, not two", twice.length, 1);
  for (const one of twice) await send("Target.closeTarget", { targetId: one.targetId });
  await gone();

  const value = "k".repeat(64);
  const expires = Math.floor(Date.now() / 1000) + 86400;
  await send("Network.enable", {}, connect.sessionId);
  const set = await send("Network.setCookie", { name: "clal", value, url: `${GATEWAY_PAGE}login/`, domain: "lng-tgk-aime-gw.am-all.net", path: "/common_auth/login", httpOnly: true, secure: true, expires }, connect.sessionId);
  expect("the HttpOnly cookie is set", set.success, true);

  expect("with the cookie the press posts the page's form", await popup.press(), "Sent.");
  await until(() => evaluate(connect.sessionId, "location.pathname"), (path) => path.startsWith("/connected/"));
  expect("the site got the form's fields and the cookie under the declared name", posted, [{ code: "test", user: "someone", token: value }]);
  expect("and the page followed the site's redirect", await evaluate(connect.sessionId, "location.pathname + location.search"), "/connected/?player=test");

  const field = await open(`${SITE}/field/`);
  await loaded(field.sessionId);
  popup = await popupOn(field.targetId);
  expect("a page with only a marked field gets the fill button", await popup.label(), "Fill it in | localhost:3000");
  expect("the card says a sign-in is there, without showing it", [await popup.card(), await evaluate(popup.sessionId, `document.body.innerText.includes(${JSON.stringify(value.slice(0, 8))})`)], ["found / ", false]);
  expect("the press fills it", await popup.press(), "Filled in.");
  expect("the page's own check accepts the value", await evaluate(field.sessionId, "document.getElementById('state').textContent"), "valid:64");
  expect("nothing more was posted", posted.length, 1);
  expect("the second button copies from any page, leaving the page alone", [(await popup.press(true, "copy")).startsWith("Copied"), await evaluate(popup.sessionId, "navigator.clipboard.readText()"), posted.length], [true, value, 1]);

  const unlisted = await open(`${SITE}/field/?unlisted`);
  await loaded(unlisted.sessionId);
  popup = await popupOn(unlisted.targetId);
  expect("a page with no grant is not a verified bot", await popup.who(), "not a verified bot");
  expect("its first press only warns, and fills nothing", [await popup.press(), await popup.label(), await evaluate(unlisted.sessionId, "document.getElementById('state').textContent")],
    ["Not a verified bot. Only send if you trust this site.", "Send anyway | localhost:3000", "invalid:0"]);
  expect("the second press goes through", [await popup.press(), await evaluate(unlisted.sessionId, "document.getElementById('state').textContent")], ["Filled in.", "valid:64"]);

  const plain = await open(`http://plain.test:${PORT}/field/`);
  await loaded(plain.sessionId);
  popup = await popupOn(plain.targetId);
  expect("a page that is not https is never typed into, only copied for", await popup.label(), "Copy sign-in | ");

  const bare = await open(`${SITE}/`);
  await loaded(bare.sessionId);
  popup = await popupOn(bare.targetId);
  expect("a page with nothing declared gets the copy button, naming no site", [await popup.label(), await evaluate(popup.sessionId, "document.getElementById('goes').hidden")], ["Copy sign-in | ", true]);
  expect("where the main button already copies, the second one is hidden", await evaluate(popup.sessionId, "document.getElementById('copy').hidden"), true);
  expect("the press copies", (await popup.press()).startsWith("Copied"), true);
  expect("the clipboard holds the value", await evaluate(popup.sessionId, "navigator.clipboard.readText()"), value);

  const paste = async (url) => {
    await evaluate(popup.sessionId, `(() => { const f = document.getElementById('link'); f.value = ${JSON.stringify(url)}; document.getElementById('lead').textContent = 'pending'; f.dispatchEvent(new Event('input', { bubbles: true })); })()`);
    const lead = () => evaluate(popup.sessionId, "document.getElementById('lead').textContent");
    await until(lead, (text) => text !== "pending" && text !== "Checking…");
    return { label: await popup.label(), lead: await lead() };
  };
  let seen = await paste(`${LINKS}/not-a-link`);
  expect("an address that is not a link is refused, the button dead", [seen.lead, await evaluate(popup.sessionId, "document.getElementById('go').disabled")], ["This site doesn't take sign-ins from the extension.", true]);
  seen = await paste("http://example.com/link/abc");
  expect("a link that is not https is refused", seen.lead, "Not a link. It has to start with https://");
  seen = await paste(`${LINKS}/link/gone`);
  expect("a dead link shows the site's own words", seen.lead, "That link has expired.");
  seen = await paste(`${LINKS}/link/waiting`);
  expect("a link whose site is not ready says what to do, and sends nothing", [await popup.press(), linked.length], ["Pass the check first.", 0]);
  seen = await paste(`${LINKS}/link/abc`);
  expect("a live link names its host, and the bot its grant was signed for", [seen.label, seen.lead, await popup.who()], [`Send | localhost:${PORT + 1}`, "", "✓ Test bot"]);
  await evaluate(popup.sessionId, "(() => { const f = document.getElementById('link'); f.value = ''; f.dispatchEvent(new Event('input', { bubbles: true })); })()");
  await popup.press(false);
  await sleep(900);
  expect("a press on an edit not read yet sends nothing and copies nothing", [linked.length, await popup.label(), await evaluate(popup.sessionId, "document.getElementById('said').textContent")], [0, "Copy sign-in | ", ""]);
  seen = await paste(`${LINKS}/link/abc`);
  expect("the press sends the sign-in to the link", await popup.press(), "Linked as TEST.");
  expect("the bot got the cookie, and only that", linked, [{ clal: value }]);
  expect("and the card shows it went", await popup.card(), "sent / ");
  expect("the button turns into a done state", [await evaluate(popup.sessionId, "document.getElementById('go').textContent"), await evaluate(popup.sessionId, "'done' in document.getElementById('go').dataset")], ["Linked ✓", true]);

  seen = await paste(`${LINKS}/link/slow`);
  expect("a new link clears the done state", [seen.label, await evaluate(popup.sessionId, "'done' in document.getElementById('go').dataset")], [`Send | localhost:${PORT + 1}`, false]);
  await popup.press(false);
  const mid = await until(() => evaluate(popup.sessionId, "[document.getElementById('spin').hidden, document.getElementById('go').getAttribute('aria-busy'), document.getElementById('go').textContent].join(' ')"), (text) => text.startsWith("false"), 1200);
  expect("while the bot answers, the button spins and says so", mid, "false true Sending…");
  expect("then it says who was linked", await until(() => evaluate(popup.sessionId, "document.getElementById('said').textContent"), (text) => text !== ""), "Linked as SLOW.");
  for (const [path, why] of [["stranger", "no grant"], ["borrowed", "another site's grant"], ["stale", "a grant past its date"]]) {
    await paste(`${LINKS}/link/${path}`);
    expect(`a link with ${why} is not a verified bot`, await popup.who(), "not a verified bot");
  }
  await paste(`${LINKS}/link/stranger`);
  const before = linked.length;
  expect("an unverified link's first press only warns, and sends nothing", [await popup.press(), linked.length - before], ["Not a verified bot. Only send if you trust this site.", 0]);
  expect("the second press sends", [await popup.press(), linked.length - before], ["Linked as TEST.", 1]);
  expect("and the spinner goes", await evaluate(popup.sessionId, "document.getElementById('spin').hidden + ' ' + document.getElementById('go').hasAttribute('aria-busy')"), "true false");

  const landed = (session) => until(() => evaluate(session, "location.pathname + location.search"), (at) => at.startsWith("/connected/"));
  consent = await asking("/oauth/authorize?client_id=test");
  approving = await approval(consent);
  await approving.press("go", false);
  expect("while rasmai.lol answers, Approve spins and says so, and Decline is held",
    await until(() => evaluate(approving.sessionId, "[document.getElementById('spin').hidden, document.getElementById('go').getAttribute('aria-busy'), document.getElementById('go').textContent, document.getElementById('no').disabled].join(' ')"), (text) => text.startsWith("false"), 600),
    "false true Approving… true");
  expect("signed in, Approve sends rasmai.lol the ticket, the sign-in and when it runs out, and the tab goes where rasmai.lol answered",
    [await landed(consent.sessionId), decided], ["/connected/?code=c1&state=s1", [["approve", { ticket: TICKET, clal: value, expires: String(expires) }]]]);
  expect("and the approval window closes itself", await gone(), true);

  consent = await asking("/oauth/authorize?client_id=test");
  approving = await approval(consent);
  await approving.press("no", false);
  expect("Decline sends only the ticket, and the tab goes back to the app with the refusal",
    [await landed(consent.sessionId), decided.slice(1), await gone()], ["/connected/?error=access_denied&state=s1", [["deny", { ticket: TICKET }]], true]);

  consent = await asking("/oauth/authorize?gone");
  approving = await approval(consent);
  expect("a ticket that has run out says so, and leaves nothing to press",
    [await approving.said(), await evaluate(approving.sessionId, "document.getElementById('ask').hidden"), await approving.close()], ["This request expired. Go back to the app and try again.", true, true]);

  const refused = [];
  for (const how of Object.keys(FORGED)) {
    consent = await asking(`/oauth/authorize?forged=${how}`);
    approving = await approval(consent);
    refused.push([how, await approving.said(), await evaluate(approving.sessionId, "document.getElementById('ask').hidden"), await approving.close()]);
  }
  expect("an answer rasmai.lol did not sign for this ticket is not shown: unsigned, signed by a stranger, signed for another ticket, or a grant",
    refused, Object.keys(FORGED).map((how) => [how, "Couldn't confirm this request came from Rasmai.", true, true]));

  consent = await asking("/oauth/authorize?reviews=off");
  approving = await approval(consent);
  expect("when rasmai.lol reviews no apps, the window speaks of no review: no badge, and a plain word of caution",
    [await evaluate(approving.sessionId, "[document.getElementById('badge').hidden, document.getElementById('unreviewed').hidden, document.getElementById('unreviewed').textContent, document.getElementById('for').parentNode.hidden]"), await approving.close()],
    [[true, false, "Only approve this if you trust the app.", true], true]);

  consent = await asking("/oauth/authorize?who=1");
  approving = await approval(consent);
  expect("the window says who a link is for, as rasmai.lol signed it",
    [await evaluate(approving.sessionId, "[document.getElementById('for').textContent, document.getElementById('for').parentNode.hidden]"), await approving.close()],
    [["nek_ng on Discord", false], true]);

  const drawn = [];
  for (const how of Object.keys(ICONS)) {
    consent = await asking(`/oauth/authorize?icon=${how}`);
    approving = await approval(consent);
    await sleep(700);
    drawn.push([how, await evaluate(approving.sessionId, "(() => { const icon = document.getElementById('icon'); return [icon.hidden, icon.naturalWidth]; })()"), await approving.close()]);
  }
  expect("the app's picture is shown when it is the one rasmai.lol signed the mark of, and left out when the bytes are another picture's",
    drawn, [["shown", [false, 1], true], ["swapped", [true, 0], true]]);

  const elsewhere = await asking("/elsewhere/");
  await really(elsewhere.sessionId, "yes");
  await sleep(700);
  expect("the same button on any other page of the site is left alone",
    [await evaluate(elsewhere.sessionId, "document.documentElement.hasAttribute('data-aime-helper')"), await marked(elsewhere.sessionId), (await windows()).length], [false, false, 0]);
  expect("the window opens only for the consent page, not the popup or anything else of the extension's",
    [await evaluate(popup.sessionId, `chrome.runtime.sendMessage({ type: "oauth", ticket: ${JSON.stringify(TICKET)} })`), (await windows()).length, decided.length],
    [{ ok: false, error: "This page can't ask for that." }, 0, 2]);

  consent = await asking("/oauth/authorize?where=1");
  approving = await approval(consent);
  expect("an answer that would send the tab somewhere other than the host rasmai.lol signed is refused, and the tab stays",
    [await approving.press("go"), await evaluate(consent.sessionId, "location.pathname"), (await windows()).length],
    ["That isn't where this request said it would send you, so the tab was not moved.", "/oauth/authorize", 1]);
} catch (error) {
  failures.push(String(error));
  console.log("FAIL  the test itself:", String(error.stack ?? error));
} finally {
  chrome.kill();
  server.close();
  links.close();
  console.log(failures.length ? `${failures.length} failed` : "all passed");
  process.exit(failures.length ? 1 : 0);
}
