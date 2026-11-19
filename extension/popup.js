const button = document.getElementById("go");
const copyButton = document.getElementById("copy");
const said = document.getElementById("said");
const lead = document.getElementById("lead");
const dest = document.getElementById("dest");
const card = document.getElementById("card");
const goes = document.getElementById("goes");
const spin = document.getElementById("spin");
const who = document.getElementById("who");
let tab = null;
const linkField = document.getElementById("link");
let way = "copy";
let link = null;
let typing;
let busy = false;
let lastRead = "";
let known = "";
let sure = false;

function showWho(name) {
  known = name;
  sure = false;
  who.textContent = name ? `✓ ${name}` : "not a verified bot";
  who.className = name ? "ok" : "no";
}

function say(text, bad = false, href = "") {
  said.textContent = text;
  said.className = bad ? "bad" : "";
  if (href) {
    const a = document.createElement("a");
    a.href = href;
    a.target = "_blank";
    a.rel = "noopener";
    a.textContent = "Sign in";
    said.append(" ", a);
  }
}

function showCard(state) {
  card.dataset.state = state;
  document.getElementById("badge").textContent = { found: "signed in", none: "not signed in", sent: "sent", unknown: "not checked" }[state];
  const until = document.getElementById("until");
  until.textContent = "";
  if (state === "none") {
    const a = document.createElement("a");
    a.href = GATEWAY_LOGIN;
    a.target = "_blank";
    a.rel = "noopener";
    a.textContent = "Sign in on the maimai site";
    until.append(a);
  }
}

async function peek() {
  try {
    if (!(await api.permissions.contains({ origins: [`https://${GATEWAY_HOST}/*`] }))) return;
    const [active] = await api.tabs.query({ active: true, currentWindow: true });
    const cookie = await signIn(active?.id);
    showCard(cookie ? "found" : "none");
  } catch {

  }
}

function onPage(value) {
  const form = document.querySelector("form[data-aime-link]");
  const field = document.querySelector('input[name="clal"], [data-aime-cookie]');
  if (!value) return { way: form ? "post" : field ? "fill" : "copy", grant: document.querySelector("[data-aime-grant]")?.getAttribute("data-aime-grant") || "" };
  if (form) {
    const action = new URL(form.getAttribute("action") || location.href, location.href);
    if (action.origin !== location.origin || (action.protocol !== "https:" && !["localhost", "127.0.0.1"].includes(action.hostname))) return { error: "the form sends to another site, so it was blocked" };
    const body = new URLSearchParams(new FormData(form));
    body.set(form.dataset.aimeLink || "token", value);
    return fetch(action, { method: (form.getAttribute("method") || "post").toUpperCase(), body, credentials: "same-origin", headers: { Accept: "text/html" } })
      .then((response) => {
        if (response.redirected) location.href = response.url;
        return { posted: true, status: response.status, redirected: response.redirected };
      })
      .catch((error) => ({ error: String(error) }));
  }
  if (!field) return { error: "the box on this page is gone" };
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
  const { host, origin, protocol, hostname } = new URL(tab?.url || "about:blank");
  let found = null;
  try {
    found = tab?.id && (protocol === "https:" || (protocol === "http:" && ["localhost", "127.0.0.1"].includes(hostname))) ? await inPage("") : null;
  } catch {
    found = null;
  }
  way = found?.way || "copy";
  showWho(way === "copy" ? "" : await bot(found.grant, origin));
  lead.textContent = "";
  delete button.dataset.done;
  dest.textContent = way === "copy" ? "" : host;
  goes.hidden = way === "copy";
  button.textContent = way === "post" ? "Link my account" : way === "fill" ? "Fill it in" : "Copy sign-in";
  button.disabled = false;
  copyButton.hidden = way === "copy";
}

async function readLink() {
  lastRead = linkField.value.trim();
  link = null;
  say("");
  if (!linkField.value.trim()) return look();
  const url = linkUrl(linkField.value);
  button.disabled = true;
  button.textContent = "Send";
  delete button.dataset.done;
  copyButton.hidden = false;
  goes.hidden = !url;
  dest.textContent = url ? url.host : "";
  showWho("");
  who.textContent = "";
  if (!url) {
    lead.textContent = "Not a link. It has to start with https://";
    return;
  }
  lead.textContent = "Checking…";
  try {
    const { data } = await ask(url);
    if (url.href !== linkUrl(linkField.value)?.href) return;
    if (data.aimeLink !== 1) {
      lead.textContent = typeof data.error === "string" ? data.error.slice(0, 200) : "This site doesn't take sign-ins from the extension.";
      return;
    }
    showWho(await bot(data.grant, url.origin));
    if (url.href !== linkUrl(linkField.value)?.href) return;
    link = { url };
    lead.textContent = "";
    button.disabled = false;
  } catch {
    lead.textContent = "Couldn't reach it.";
  }
}

async function sendToLink(link, value) {
  const done = await handOver(link.url, value);
  if (!done.ok) return say(done.error, true);
  say(`Linked${done.player ? ` as ${done.player}` : ""}.`);
  linkField.value = "";
  lastRead = "";
  return true;
}

async function signedIn() {
  // Firefox: permissions.request has to be the first await of a click
  if (!(await api.permissions.request({ origins: [`https://${GATEWAY_HOST}/*`] }))) {
    say("It needs permission to read your maimai sign-in.", true);
    return null;
  }
  const cookie = await signIn(tab?.id);
  showCard(cookie ? "found" : "none");
  if (!cookie) say("Not signed in.", true, GATEWAY_LOGIN);
  return cookie ?? null;
}

async function toClipboard(cookie) {
  await navigator.clipboard.writeText(cookie.value);
  say("Copied.");
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

function sending(on) {
  spin.hidden = !on;
  if (on) {
    button.textContent = "Sending…";
    button.setAttribute("aria-busy", "true");
  } else {
    button.removeAttribute("aria-busy");
  }
}

function finished(text) {
  button.dataset.done = "";
  button.textContent = text;
}

async function go() {
  clearTimeout(typing);
  if (linkField.value.trim() !== lastRead) return readLink();
  if (busy) return;
  if ((link || way !== "copy") && !known && !sure) {
    sure = true;
    button.textContent = "Send anyway";
    say("Not a verified bot. Only send if you trust this site.", true);
    return;
  }
  busy = true;
  const target = link;
  const how = way;
  const label = button.textContent;
  button.disabled = true;
  linkField.disabled = true;
  try {
    const cookie = await signedIn();
    if (!cookie) return;
    if (target) {
      sending(true);
      if (await sendToLink(target, cookie.value)) {
        link = null;
        showCard("sent");
        finished("Linked ✓");
      }
      return;
    }
    if (how === "copy") {
      await toClipboard(cookie);
      return;
    }
    if (how === "post") sending(true);
    const result = await inPage(cookie.value);
    if (!result || result.error) {
      say(`Didn't work: ${result?.error ?? "the page didn't respond"}`, true);
    } else if (result.filled) {
      say("Filled in.");
      showCard("sent");
    } else if (result.redirected) {
      say("Sent.");
      showCard("sent");
      finished("Sent ✓");
    } else {
      say(result.status < 400 ? "Sent." : `Error ${result.status}.`, result.status >= 400);
    }
  } catch (error) {
    say(`Didn't work: ${error && error.message ? error.message : error}`, true);
  } finally {
    busy = false;
    sending(false);
    linkField.disabled = false;
    if (!("done" in button.dataset)) {
      button.textContent = label;
      button.disabled = false;
    }
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
