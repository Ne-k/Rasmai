const query = new URLSearchParams(location.search);
const ticket = query.get("ticket") ?? "";
const tab = Number(query.get("tab"));
const approve = document.getElementById("go");
const decline = document.getElementById("no");
const said = document.getElementById("said");
const spin = document.getElementById("spin");
// where rasmai.lol signed that the player is sent: the tab goes nowhere else
let shownHost = "";
const WORDS = new Map([
  ["expired", "This request expired. Go back to the app and try again."],
  ["bad_clal", "That sign-in didn't work. Sign in on the maimai site again."],
]);

const text = (value, most) => (typeof value === "string" ? value.slice(0, most) : "");
const wrong = ({ status, data }) => WORDS.get(data.error) ?? (text(data.error, 200) || `Error ${status}.`);

function web(value) {
  try {
    const url = new URL(value);
    return url.protocol === "https:" || url.protocol === "http:" ? url.href : "";
  } catch {
    return "";
  }
}

function link(href, label) {
  const a = document.createElement("a");
  a.href = href;
  a.target = "_blank";
  a.rel = "noopener";
  a.textContent = label;
  return a;
}

function say(words, bad = false, href = "") {
  said.textContent = words;
  said.className = bad ? "bad" : "";
  if (href) said.append(" ", link(href, "Sign in"));
}

function row(id, value, linked = false) {
  const cell = document.getElementById(id);
  const href = linked ? web(value) : "";
  cell.textContent = href ? "" : value;
  if (href) cell.append(link(href, value));
  cell.parentNode.hidden = !value;
}

async function picture(path) {
  const mark = /^\/api\/oauth\/icon\/[\w-]{24}\?v=([0-9a-f]{32})$/.exec(path)?.[1];
  if (!mark) return;
  const response = await fetch(HOME + path, { redirect: "error", credentials: "omit" });
  const data = await response.arrayBuffer();
  const digest = Array.from(new Uint8Array(await crypto.subtle.digest("SHA-256", data)), (byte) => byte.toString(16).padStart(2, "0")).join("");
  if (!response.ok || !digest.startsWith(mark)) return;
  const icon = document.getElementById("icon");
  icon.src = URL.createObjectURL(new Blob([data], { type: "image/png" }));
  icon.hidden = false;
}

async function load() {
  const answer = await ask(`${HOME}/api/oauth/request/${encodeURIComponent(ticket)}`);
  if (answer.data.ok !== true) return say(wrong(answer), true);
  const asked = await signedBy("aime-oauth.", answer.data.signed);
  const app = asked?.v === 1 && asked.ticket === ticket && asked.exp * 1000 > Date.now() && asked.app;
  const host = text(asked?.redirectHost, 200);
  if (!app || !host) return say("Couldn't confirm this request came from Rasmai.", true);
  const name = text(app.name, 40) || "This app";
  const reviewed = app.verified === true;
  document.getElementById("title").textContent = `${name} wants your maimai sign-in`;
  row("app", name);
  row("by", text(app.by, 80));
  row("for", text(asked.for, 48));
  row("dest", host);
  shownHost = host;
  row("website", text(app.website, 200), true);
  row("privacy", text(app.privacy, 200), true);
  picture(text(app.icon, 80)).catch(() => {});
  document.getElementById("card").dataset.state = reviewed ? "verified" : "unreviewed";
  const reviews = asked.reviews !== false;
  const badge = document.getElementById("badge");
  badge.textContent = reviewed ? "verified" : "not reviewed";
  badge.hidden = !reviewed && !reviews;
  const warning = document.getElementById("unreviewed");
  warning.hidden = reviewed;
  if (!reviews) warning.textContent = "Only approve this if you trust the app.";
  document.getElementById("ask").hidden = false;
  approve.disabled = decline.disabled = false;
}

function sending(button, words) {
  button.after(spin);
  spin.hidden = false;
  button.textContent = words;
  button.setAttribute("aria-busy", "true");
}

async function finish(answer) {
  const redirect = answer.data.ok === true ? web(answer.data.redirect) : "";
  if (!redirect) {
    say(wrong(answer), true);
    return answer.data.error !== "expired";
  }
  if (new URL(redirect).host !== shownHost) {
    say("That isn't where this request said it would send you, so the tab was not moved.", true);
    return false;
  }
  try {
    await api.tabs.update(tab, { url: redirect, active: true });
  } catch {
    await api.tabs.create({ url: redirect });
  }
  api.tabs.remove((await api.tabs.getCurrent()).id);
  return false;
}

async function approved() {
  // Firefox: permissions.request has to be the first await of a click
  if (!(await api.permissions.request({ origins: [GATEWAY] }))) {
    say("It needs permission to read your maimai sign-in.", true);
    return true;
  }
  const cookie = await signIn(tab);
  if (!cookie) {
    say("Not signed in.", true, GATEWAY_LOGIN);
    return true;
  }
  sending(approve, "Approving…");
  const body = new URLSearchParams({ ticket, clal: cookie.value });
  if (cookie.expirationDate) body.set("expires", Math.floor(cookie.expirationDate));
  return finish(await ask(`${HOME}/api/oauth/approve`, body));
}

async function declined() {
  sending(decline, "Declining…");
  return finish(await ask(`${HOME}/api/oauth/deny`, new URLSearchParams({ ticket })));
}

async function press(act) {
  approve.disabled = decline.disabled = true;
  say("");
  let open = true;
  try {
    open = await act();
  } catch (error) {
    say(`Didn't work: ${error?.message ?? error}`, true);
  } finally {
    spin.hidden = true;
    for (const [button, label] of [[approve, "Approve"], [decline, "Decline"]]) {
      button.removeAttribute("aria-busy");
      button.textContent = label;
      button.disabled = !open;
    }
  }
}

approve.addEventListener("click", () => press(approved));
decline.addEventListener("click", () => press(declined));
load().catch(() => say("Couldn't reach it.", true));
