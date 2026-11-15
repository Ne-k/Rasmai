import { spawn } from "node:child_process";
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
const without = (html, part) => html.replace(new RegExp(`<!--${part}-->[\\s\\S]*?<!--/${part}-->`), "");
const posted = [];
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
  const html = request.url.startsWith("/connect/") ? page : request.url.startsWith("/field/") ? without(page, "FORM")
    : request.url.startsWith("/connected/") ? "<h1 id='linked'>linked</h1>" : without(without(page, "FORM"), "FIELD");
  response.writeHead(200, { "Content-Type": "text/html" });
  response.end(html);
}).listen(PORT, "127.0.0.1");

const LINKS = `http://localhost:${PORT + 1}`;
const linked = [];
const links = createServer((request, response) => {
  const answer = (status, body) => { response.writeHead(status, { "Content-Type": "application/json", "Access-Control-Allow-Origin": "*" }); response.end(JSON.stringify(body)); };
  if (request.url === "/not-a-link") return answer(200, { hello: "world" });
  if (request.url === "/link/waiting") return answer(200, { aimeLink: 1, site: "Test bot", ready: false, wait: "Pass the check first." });
  if (request.url !== "/link/abc") return answer(404, { error: "That link has expired." });
  if (request.method === "GET") return answer(200, { aimeLink: 1, site: "Test bot", ready: true });
  let body = "";
  request.on("data", (chunk) => { body += chunk; });
  request.on("end", () => { linked.push(Object.fromEntries(new URLSearchParams(body))); answer(200, { ok: true, player: "TEST" }); });
}).listen(PORT + 1, "127.0.0.1");

const work = mkdtempSync(join(tmpdir(), "aime-helper-"));
const copy = join(work, "extension");
cpSync(SOURCE, copy, { recursive: true, filter: (path) => !path.startsWith(HERE) });
const manifest = JSON.parse(readFileSync(join(copy, "manifest.json"), "utf8"));
manifest.host_permissions.push(`${SITE}/*`, `http://plain.test:${PORT}/*`);
delete manifest.browser_specific_settings;
writeFileSync(join(copy, "manifest.json"), JSON.stringify(manifest));

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
    const label = () => evaluate(action.sessionId, "document.getElementById('go').textContent + ' | ' + document.getElementById('dest').textContent");
    const said = () => evaluate(action.sessionId, "document.getElementById('said').textContent");
    await until(label, (text) => !text.startsWith("…"));
    return {
      ...action,
      label,
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
  expect("the card says nobody is signed in", (await popup.card()).startsWith("none / Sign in on the maimai site"), true);
  expect("without a cookie the popup says to sign in", (await popup.press()).startsWith("You're not signed in"), true);
  expect("and posts nothing", posted.length, 0);

  const value = "k".repeat(64);
  await send("Network.enable", {}, connect.sessionId);
  const set = await send("Network.setCookie", { name: "clal", value, url: `${GATEWAY_PAGE}login/`, domain: "lng-tgk-aime-gw.am-all.net", path: "/common_auth/login", httpOnly: true, secure: true }, connect.sessionId);
  expect("the HttpOnly cookie is set", set.success, true);

  expect("with the cookie the press posts the page's form", await popup.press(), "Sent. The page is loading.");
  await until(() => evaluate(connect.sessionId, "location.pathname"), (path) => path.startsWith("/connected/"));
  expect("the site got the form's fields and the cookie under the declared name", posted, [{ code: "test", user: "someone", token: value }]);
  expect("and the page followed the site's redirect", await evaluate(connect.sessionId, "location.pathname + location.search"), "/connected/?player=test");

  const field = await open(`${SITE}/field/`);
  await loaded(field.sessionId);
  popup = await popupOn(field.targetId);
  expect("a page with only a marked field gets the fill button", await popup.label(), "Fill it in | localhost:3000");
  expect("the card says a sign-in is there, without showing it", [(await popup.card()).startsWith("found / "), await evaluate(popup.sessionId, `document.body.innerText.includes(${JSON.stringify(value.slice(0, 8))})`)], [true, false]);
  expect("the press fills it", await popup.press(), "Filled in. Finish on the page.");
  expect("the page's own check accepts the value", await evaluate(field.sessionId, "document.getElementById('state').textContent"), "valid:64");
  expect("nothing more was posted", posted.length, 1);
  expect("the second button copies from any page, leaving the page alone", [(await popup.press(true, "copy")).startsWith("Copied"), await evaluate(popup.sessionId, "navigator.clipboard.readText()"), posted.length], [true, value, 1]);

  const plain = await open(`http://plain.test:${PORT}/field/`);
  await loaded(plain.sessionId);
  popup = await popupOn(plain.targetId);
  expect("a page that is not https is never typed into, only copied for", await popup.label(), "Copy it | your clipboard");

  const bare = await open(`${SITE}/`);
  await loaded(bare.sessionId);
  popup = await popupOn(bare.targetId);
  expect("a page with nothing declared gets the copy button", await popup.label(), "Copy it | your clipboard");
  expect("where the main button already copies, the second one is hidden", await evaluate(popup.sessionId, "document.getElementById('copy').hidden"), true);
  expect("the press copies", (await popup.press()).startsWith("Copied"), true);
  expect("the clipboard holds the value", await evaluate(popup.sessionId, "navigator.clipboard.readText()"), value);

  const paste = async (url) => {
    await evaluate(popup.sessionId, `(() => { const f = document.getElementById('link'); f.value = ${JSON.stringify(url)}; document.getElementById('lead').textContent = 'pending'; f.dispatchEvent(new Event('input', { bubbles: true })); })()`);
    const lead = () => evaluate(popup.sessionId, "document.getElementById('lead').textContent");
    await until(lead, (text) => text !== "pending" && !text.startsWith("Checking "));
    return { label: await popup.label(), lead: await lead() };
  };
  let seen = await paste(`${LINKS}/not-a-link`);
  expect("an address that is not a link is refused, the button dead", [seen.lead.includes("isn't set up for this extension"), await evaluate(popup.sessionId, "document.getElementById('go').disabled")], [true, true]);
  seen = await paste("http://example.com/link/abc");
  expect("a link that is not https is refused", seen.lead.includes("has to start with https://"), true);
  seen = await paste(`${LINKS}/link/gone`);
  expect("a dead link shows the site's own words", seen.lead, "That link has expired.");
  seen = await paste(`${LINKS}/link/waiting`);
  expect("a link whose site is not ready says what to do, and sends nothing", [await popup.press(), linked.length], ["Pass the check first.", 0]);
  seen = await paste(`${LINKS}/link/abc`);
  expect("a live link names its host on the button", seen.label, `Send it | localhost:${PORT + 1}`);
  expect("and the lead names the host before what the site calls itself", seen.lead.startsWith(`localhost:${PORT + 1} (calls itself Test bot)`), true);
  await evaluate(popup.sessionId, "(() => { const f = document.getElementById('link'); f.value = ''; f.dispatchEvent(new Event('input', { bubbles: true })); })()");
  await popup.press(false);
  await sleep(900);
  expect("a press on an edit not read yet sends nothing and copies nothing", [linked.length, await popup.label(), await evaluate(popup.sessionId, "document.getElementById('said').textContent")], [0, "Copy it | your clipboard", ""]);
  seen = await paste(`${LINKS}/link/abc`);
  expect("the press sends the sign-in to the link", await popup.press(), "Linked as TEST. You can close this.");
  expect("the bot got the cookie, and only that", linked, [{ clal: value }]);
  expect("and the card shows it went", (await popup.card()).startsWith("sent / "), true);
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
