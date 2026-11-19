const api = globalThis.browser ?? globalThis.chrome;

document.documentElement.setAttribute("data-aime-helper", api.runtime.getManifest().version);
document.dispatchEvent(new Event("aime-helper"));

// only a real press counts: a script on the page can't make one
let opened = 0;
document.addEventListener("click", async (event) => {
  const button = event.target instanceof Element ? event.target.closest("[data-aime-oauth]") : null;
  if (!button || !event.isTrusted || button.hasAttribute("data-aime-busy") || Date.now() - opened < 3000) return;
  button.setAttribute("data-aime-busy", "");
  const answer = await api.runtime.sendMessage({ type: "oauth", ticket: button.getAttribute("data-aime-ticket") }).catch(() => null);
  button.removeAttribute("data-aime-busy");
  if (!answer?.ok) return;
  opened = Date.now();
  button.setAttribute("data-aime-opened", "");
  button.dispatchEvent(new Event("aime-opened", { bubbles: true }));
}, true);
