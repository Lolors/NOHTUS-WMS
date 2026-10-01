const CACHE_NAME = "nohtus-mobile-shell-v11";
const CACHE_PREFIX = "nohtus-mobile-shell-";
const SHELL_FILES = ["./", "./index.html", "./styles.css?v=5", "./app.js?v=6", "./manifest.json"];

self.addEventListener("install", (event) => {
  event.waitUntil((async () => {
    const cache = await caches.open(CACHE_NAME);
    await Promise.all(SHELL_FILES.map(async (file) => {
      try {
        const response = await fetch(new Request(file, { cache: "reload" }));
        if (response.ok) await cache.put(file, response);
      } catch (error) {
        console.warn("sw install: failed to cache", file, error);
      }
    }));
    await self.skipWaiting();
  })());
});

self.addEventListener("activate", (event) => {
  event.waitUntil((async () => {
    const keys = await caches.keys();
    await Promise.all(keys.filter((key) => key.startsWith(CACHE_PREFIX) && key !== CACHE_NAME).map((key) => caches.delete(key)));
    await self.clients.claim();
  })());
});

self.addEventListener("fetch", (event) => {
  const url = new URL(event.request.url);
  if (url.origin !== self.location.origin || url.pathname.includes("/api/") || event.request.method !== "GET") return;
  event.respondWith((async () => {
    const cache = await caches.open(CACHE_NAME);
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 5000);
    try {
      // Online requests always revalidate; cache is only the offline fallback.
      const response = await fetch(event.request, { cache: "no-cache", signal: controller.signal });
      if (response.ok) {
        try { await cache.put(event.request, response.clone()); } catch (_) { /* quota/storage unavailable */ }
      }
      return response;
    } catch (_) {
      const cached = await cache.match(event.request);
      if (cached) return cached;
      if (event.request.mode === "navigate") {
        const shell = await cache.match(new URL("./index.html", self.registration.scope).href);
        if (shell) return shell;
      }
      return new Response("네트워크 연결을 확인한 뒤 다시 실행해 주세요.", {
        status: 503, headers: { "Content-Type": "text/plain; charset=utf-8" },
      });
    } finally {
      clearTimeout(timeout);
    }
  })());
});
