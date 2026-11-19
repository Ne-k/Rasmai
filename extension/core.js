const api = globalThis.browser ?? globalThis.chrome;
const GATEWAY_HOST = "lng-tgk-aime-gw.am-all.net";
const GATEWAY = `https://${GATEWAY_HOST}/*`;
const GATEWAY_LOGIN = `https://${GATEWAY_HOST}/common_auth/login?site_id=maimaidxex&redirect_url=https://maimaidx-eng.com/maimai-mobile/&back_url=https://maimai.sega.com/`;
// rasmai.lol's grant keys, current then next
const GRANT_KEYS = ["M0LrAExCamq5MP8PG5FzLsnpNxV-CYz1EB_Jw98jT2A"];
const HOME = "https://rasmai.lol";

const bytes = (text) => Uint8Array.from(atob(text.replace(/-/g, "+").replace(/_/g, "/")), (c) => c.charCodeAt(0));

async function signedBy(prefix, note) {
  const [body, signature] = String(note ?? "").split(".");
  const signed = new TextEncoder().encode(prefix + body);
  for (const key of GRANT_KEYS) {
    try {
      const held = await crypto.subtle.importKey("raw", bytes(key), "Ed25519", false, ["verify"]);
      if (await crypto.subtle.verify("Ed25519", held, bytes(signature), signed)) return JSON.parse(new TextDecoder().decode(bytes(body)));
    } catch {
      continue;
    }
  }
  return null;
}

async function bot(grant, origin) {
  const grants = await signedBy("aime-grant.", grant);
  return grants?.v === 1 && grants.origin === origin && grants.exp * 1000 > Date.now() && typeof grants.name === "string" ? grants.name.slice(0, 40) : "";
}

async function signIn(tabId) {
  const store = (await api.cookies.getAllCookieStores()).find((each) => each.tabIds.includes(tabId));
  const cookies = await api.cookies.getAll({ domain: GATEWAY_HOST, name: "clal", ...(store ? { storeId: store.id } : {}) });
  return cookies.find((c) => /^[A-Za-z0-9]{64}$/.test(c.value));
}

function linkUrl(text) {
  try {
    const url = new URL(String(text).trim());
    return url.protocol === "https:" || (url.protocol === "http:" && ["localhost", "127.0.0.1"].includes(url.hostname)) ? url : null;
  } catch {
    return null;
  }
}

async function ask(url, body) {
  const response = await fetch(url, { method: body ? "POST" : "GET", body, redirect: "error", credentials: "omit", cache: "no-store" });
  return { status: response.status, data: await response.json().catch(() => ({})) };
}

async function handOver(url, value) {
  const { data: now } = await ask(url);
  if (now.aimeLink !== 1) return { ok: false, error: typeof now.error === "string" ? now.error.slice(0, 200) : "That link doesn't work anymore." };
  if (now.ready === false) return { ok: false, error: (typeof now.wait === "string" && now.wait.slice(0, 200)) || "Finish the steps on the site first." };
  const { status, data } = await ask(url, new URLSearchParams({ clal: value }));
  if (status === 200 && data.ok === true) return { ok: true, player: typeof data.player === "string" ? data.player.slice(0, 40) : "" };
  return { ok: false, error: typeof data.error === "string" && data.error ? data.error.slice(0, 300) : `Error ${status}.` };
}
