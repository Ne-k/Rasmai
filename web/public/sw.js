// Rasmai's service worker: it makes the site installable and keeps the shell usable offline.
// Only the site's own static files are cached. Scores, sign-in and anything under /api or /auth
// always go to the network, so nothing about a player is ever stored here.
// the page registers this script with the build id in its address, so each deploy gets its own cache and the old one is dropped
const VERSION = "rasmai-shell-" + (new URL(self.location.href).searchParams.get("v") || "1");
const OFFLINE = "/offline.html";

self.addEventListener("install", (event) => {
  event.waitUntil(caches.open(VERSION).then((cache) => cache.addAll([OFFLINE])));
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) => Promise.all(keys.filter((key) => key !== VERSION).map((key) => caches.delete(key)))),
  );
  self.clients.claim();
});

const STATIC = /^\/(_next\/static\/|marks\/|app\/)/;

self.addEventListener("fetch", (event) => {
  const request = event.request;
  if (request.method !== "GET") return;
  const url = new URL(request.url);
  if (url.origin !== self.location.origin) return;
  if (url.pathname.startsWith("/api/") || url.pathname.startsWith("/auth/")) return;

  // hashed build files and the brand marks never change under the same name: serve from the cache first
  if (STATIC.test(url.pathname)) {
    event.respondWith(
      caches.open(VERSION).then(async (cache) => {
        const hit = await cache.match(request);
        if (hit) return hit;
        const fresh = await fetch(request);
        if (fresh.ok) cache.put(request, fresh.clone());
        return fresh;
      }),
    );
    return;
  }

  // pages: the network, and a plain offline page when there is none
  if (request.mode === "navigate") {
    event.respondWith(fetch(request).catch(() => caches.match(OFFLINE)));
  }
});
