const api = globalThis.browser ?? globalThis.chrome;
const GATEWAY_HOST = "lng-tgk-aime-gw.am-all.net";
const GATEWAY_LOGIN = `https://${GATEWAY_HOST}/common_auth/login?site_id=maimaidxex&redirect_url=https://maimaidx-eng.com/maimai-mobile/&back_url=https://maimai.sega.com/`;

const button = document.getElementById("go");
const copyButton = document.getElementById("copy");
const said = document.getElementById("said");
const lead = document.getElementById("lead");
const dest = document.getElementById("dest");
const card = document.getElementById("card");
let tab = null;
const linkField = document.getElementById("link");
let way = "copy";
let link = null;
let typing;
let busy = false;
let lastRead = "";

function say(text, bad = false, href = "") {
  said.textContent = text;
  said.className = bad ? "bad" : "";
  if (href) {
    const a = document.createElement("a");
    a.href = href;
    a.target = "_blank";
    a.rel = "noopener";
    a.textContent = "Open sign in";
    said.append(" ", a);
  }
}

function showCard(state, cookie) {
  card.dataset.state = state;
  document.getElementById("badge").textContent = { found: "signed in", none: "not signed in", sent: "sent", unknown: "not checked yet" }[state];
  const until = document.getElementById("until");
  if (state === "found" || state === "sent") {
    const ends = cookie?.expirationDate ? new Date(cookie.expirationDate * 1000).toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" }) : "";
    until.textContent = ends ? `Works until ${ends}.` : "Found.";
  } else if (state === "none") {
    until.textContent = "Sign in on the maimai site with auto login checked. ";
    const a = document.createElement("a");
    a.href = GATEWAY_LOGIN;
    a.target = "_blank";
    a.rel = "noopener";
    a.textContent = "Open sign in";
    until.append(a);
  }
}

async function signIn() {
  const cookies = await api.cookies.getAll({ domain: GATEWAY_HOST, name: "clal" });
  return cookies.find((c) => /^[A-Za-z0-9]{64}$/.test(c.value));
}

async function peek() {
  try {
    if (!(await api.permissions.contains({ origins: [`https://${GATEWAY_HOST}/*`] }))) return;
    const cookie = await signIn();
    showCard(cookie ? "found" : "none", cookie);
  } catch {

  }
}

function onPage(value) {
  const form = document.querySelector("form[data-aime-link]");
  const field = document.querySelector('input[name="clal"], [data-aime-cookie]');
  if (!value) return form ? "post" : field ? "fill" : "copy";
  if (form) {
    const action = new URL(form.getAttribute("action") || location.href, location.href);
    if (action.origin !== location.origin || (action.protocol !== "https:" && action.hostname !== "localhost")) return { error: "This page's form sends to a different site, so it was blocked." };
    const body = new URLSearchParams(new FormData(form));
    body.set(form.dataset.aimeLink || "token", value);
    return fetch(action, { method: (form.getAttribute("method") || "post").toUpperCase(), body, credentials: "same-origin", headers: { Accept: "text/html" } })
      .then((response) => {
        if (response.redirected) location.href = response.url;
        return { posted: true, status: response.status, redirected: response.redirected };
      })
      .catch((error) => ({ error: String(error) }));
  }
  if (!field) return { error: "The box on this page is gone." };
  // React only notices a value set through the native setter
  Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value").set.call(field, value);
  field.dispatchEvent(new Event("input", { bubbles: true }));
  field.focus();
  return { filled: true };
}

async function inPage(value) {
  const [result] = await api.scripting.executeScript({ target: { tabId: tab.id }, func: onPage, args: [value] });
  return result ? result.result : undefined;
}

async function look() {
  [tab] = await api.tabs.query({ active: true, currentWindow: true });
  const { host, protocol, hostname } = new URL(tab?.url || "about:blank");
  try {
    way = tab?.id && (protocol === "https:" || (protocol === "http:" && ["localhost", "127.0.0.1"].includes(hostname))) ? (await inPage("")) || "copy" : "copy";
  } catch {
    way = "copy";
  }
  lead.textContent = way === "post" ? "This page can link your account. Your sign-in only goes to the site above."
    : way === "fill" ? "This page has a box for your sign-in. It only goes to the site above."
    : "Nothing to fill on this page, so this copies your sign-in and you paste it where the site asks.";
  dest.textContent = way === "copy" ? "your clipboard" : host;
  button.textContent = way === "post" ? "Link my account" : way === "fill" ? "Fill it in" : "Copy it";
  button.disabled = false;
  copyButton.hidden = way === "copy";
}

function linkUrl(text) {
  try {
    const url = new URL(text.trim());
    return url.protocol === "https:" || (url.protocol === "http:" && ["localhost", "127.0.0.1"].includes(url.hostname)) ? url : null;
  } catch {
    return null;
  }
}

async function ask(url, body) {
  const response = await fetch(url, { method: body ? "POST" : "GET", body, redirect: "error", credentials: "omit", cache: "no-store" });
  return { status: response.status, data: await response.json().catch(() => ({})) };
}

async function readLink() {
  lastRead = linkField.value.trim();
  link = null;
  say("");
  if (!linkField.value.trim()) return look();
  const url = linkUrl(linkField.value);
  button.disabled = true;
  button.textContent = "Send it";
  copyButton.hidden = false;
  dest.textContent = url ? url.host : "nowhere yet";
  if (!url) {
    lead.textContent = "That's not a valid link. It has to start with https://";
    return;
  }
  lead.textContent = `Checking ${url.host}…`;
  try {
    const { data } = await ask(url);
    if (url.href !== linkUrl(linkField.value)?.href) return;
    if (data.aimeLink !== 1) {
      lead.textContent = typeof data.error === "string" ? data.error.slice(0, 200) : `${url.host} isn't set up for this extension.`;
      return;
    }
    link = { url };
    lead.textContent = `${url.host}${typeof data.site === "string" ? ` (calls itself ${data.site.slice(0, 40)})` : ""} will get your sign-in and link your account. Only send it if that's your bot.`;
    button.disabled = false;
  } catch {
    lead.textContent = `Couldn't reach ${url.host}, or it isn't set up for this extension.`;
  }
}

async function sendToLink(link, value) {
  const { data: now } = await ask(link.url);
  if (now.aimeLink !== 1) return say(typeof now.error === "string" ? now.error.slice(0, 200) : "That link doesn't work anymore.", true);
  if (now.ready === false) return say((typeof now.wait === "string" && now.wait.slice(0, 200)) || "The site isn't ready yet. Finish its steps, then try again.", true);
  const { status, data } = await ask(link.url, new URLSearchParams({ clal: value }));
  if (status === 200 && data.ok === true) {
    say(`Linked${typeof data.player === "string" && data.player ? ` as ${data.player.slice(0, 40)}` : ""}. You can close this.`);
    linkField.value = "";
    lastRead = "";
    button.textContent = "Done";
    return true;
  }
  say(typeof data.error === "string" && data.error ? data.error.slice(0, 300) : `${link.url.host} gave an error (${status}).`, true);
}

async function signedIn() {
  // Firefox: permissions.request has to be the first await of a click
  if (!(await api.permissions.request({ origins: [`https://${GATEWAY_HOST}/*`] }))) {
    say("It needs permission to read your sign-in from the maimai site. Nothing else.", true);
    return null;
  }
  const cookie = await signIn();
  showCard(cookie ? "found" : "none", cookie);
  if (!cookie) say("You're not signed in. Sign in on the maimai site with auto login checked, then try again.", true, GATEWAY_LOGIN);
  return cookie ?? null;
}

async function toClipboard(cookie) {
  await navigator.clipboard.writeText(cookie.value);
  say("Copied. Paste it where it's needed, then copy something else after to clear it.");
}

async function copy() {
  if (busy) return;
  busy = true;
  copyButton.disabled = true;
  try {
    const cookie = await signedIn();
    if (cookie) await toClipboard(cookie);
  } catch (error) {
    say(`Didn't work: ${error && error.message ? error.message : error}`, true);
  } finally {
    busy = false;
    copyButton.disabled = false;
  }
}

async function go() {
  clearTimeout(typing);
  if (linkField.value.trim() !== lastRead) return readLink();
  if (busy) return;
  busy = true;
  const target = link;
  const how = way;
  button.disabled = true;
  linkField.disabled = true;
  try {
    const cookie = await signedIn();
    if (!cookie) return;
    if (target) {
      if (await sendToLink(target, cookie.value)) {
        link = null;
        showCard("sent", cookie);
      }
      return;
    }
    if (how === "copy") {
      await toClipboard(cookie);
      return;
    }
    const result = await inPage(cookie.value);
    if (!result || result.error) {
      say(`Didn't work: ${result?.error ?? "the page didn't respond"}`, true);
    } else if (result.filled) {
      say("Filled in. Finish on the page.");
      showCard("sent", cookie);
    } else if (result.redirected) {
      say("Sent. The page is loading.");
      showCard("sent", cookie);
      button.textContent = "Done";
    } else {
      say(result.status < 400 ? "Sent." : `The site gave an error (${result.status}). Check the page.`, result.status >= 400);
    }
  } catch (error) {
    say(`Didn't work: ${error && error.message ? error.message : error}`, true);
  } finally {
    busy = false;
    linkField.disabled = false;
    if (button.textContent !== "Done") button.disabled = false;
  }
}

button.addEventListener("click", go);
copyButton.addEventListener("click", copy);
linkField.addEventListener("input", () => {
  clearTimeout(typing);
  typing = setTimeout(readLink, 400);
});
look();
peek();
