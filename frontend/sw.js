const CACHE_VERSION = "__APP_VERSION__";

self.addEventListener("install", () => {
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    (async () => {
      const keys = await caches.keys();
      await Promise.all(
        keys.filter((key) => key !== `agri-detect-${CACHE_VERSION}`).map((key) => caches.delete(key))
      );
      await self.clients.claim();
    })()
  );
});

self.addEventListener("fetch", (event) => {
  if (event.request.method !== "GET") return;
  const url = new URL(event.request.url);
  // 僅攔截本站資源，避免阻擋外部延伸連結導向
  if (url.origin !== self.location.origin) return;
  event.respondWith(fetch(event.request, { cache: "no-store" }));
});
