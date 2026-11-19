if (typeof importScripts === "function") importScripts("core.js");

async function oauth(message, sender) {
  const page = new URL(sender.url ?? "about:blank");
  if (page.origin !== HOME || !page.pathname.startsWith("/oauth/authorize") || !sender.tab) return { ok: false, error: "This page can't ask for that." };
  if (!/^[\w-]{1,128}$/.test(message.ticket ?? "")) return { ok: false, error: "That isn't a request." };
  const url = api.runtime.getURL(`approve.html?ticket=${message.ticket}&tab=${sender.tab.id}`);
  if (api.windows) await api.windows.create({ url, type: "popup", width: 420, height: 470 });
  else await api.tabs.create({ url });
  return { ok: true };
}

api.runtime.onMessage.addListener((message, sender, respond) => {
  if (message?.type !== "oauth") return false;
  oauth(message, sender).then(respond, (error) => respond({ ok: false, error: String(error?.message ?? error) }));
  return true;
});
