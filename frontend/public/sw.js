/**
 * Funduqii service worker (Phase 17) — deliberately MINIMAL and safe.
 *
 * What it does:
 *  - Pre-caches ONLY the static offline fallback page and the app icons
 *    (public, non-sensitive assets).
 *  - Serves the offline page when a NAVIGATION request fails (no network).
 *
 * What it deliberately does NOT do (security/privacy decisions, Phase 17):
 *  - No caching of API responses, console pages, or any authenticated
 *    content — hotel, guest, finance and permission data NEVER enter any
 *    cache, so nothing can leak between users or tenants.
 *  - No tokens/JWT anywhere near the cache.
 *  - No background sync, no push, no write queue, no offline operations.
 *  - Every non-navigation request passes straight to the network.
 */
// v2: "Grand Lobby" redesign — offline page + icons recolored (#166a53).
const CACHE_NAME = "funduqii-offline-v2";
const OFFLINE_URL = "/offline.html";
const PRECACHE = [
  OFFLINE_URL,
  "/icons/icon-192.png",
  "/icons/icon-512.png",
];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => cache.addAll(PRECACHE)),
  );
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches
      .keys()
      .then((keys) =>
        Promise.all(
          keys.filter((key) => key !== CACHE_NAME).map((key) => caches.delete(key)),
        ),
      )
      .then(() => self.clients.claim()),
  );
});

self.addEventListener("fetch", (event) => {
  // Only NAVIGATIONS get a fallback; everything else is network-only.
  if (event.request.mode !== "navigate") return;
  event.respondWith(
    fetch(event.request).catch(() =>
      caches.match(OFFLINE_URL).then(
        (cached) =>
          // Never let respondWith reject: if the precache is missing (e.g.
          // storage was cleared), answer with a minimal plain response.
          cached ||
          new Response("Offline — لا يوجد اتصال بالإنترنت", {
            status: 503,
            headers: { "Content-Type": "text/plain; charset=utf-8" },
          }),
      ),
    ),
  );
});
