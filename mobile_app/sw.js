const CACHE_NAME = "nohtus-mobile-shell-v4";
const SHELL_FILES = ["./", "./index.html", "./styles.css?v=2", "./app.js?v=3", "./manifest.json"];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => cache.addAll(SHELL_FILES))
  );
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((key) => key !== CACHE_NAME).map((key) => caches.delete(key)))
    )
  );
  self.clients.claim();
});

self.addEventListener("fetch", (event) => {
  const url = new URL(event.request.url);
  // API 요청은 항상 네트워크로 — 캐시하면 재고 데이터가 오래된 채로 보일 수 있다.
  // "/mobile/" 프리픽스 아래에서 서빙될 때는 "/api/..."가 아니라
  // "/mobile/api/..."로 오므로 startsWith가 아니라 includes로 확인한다.
  if (url.pathname.includes("/api/")) return;
  if (event.request.method !== "GET") return;

  event.respondWith(
    caches.match(event.request).then((cached) => {
      const network = fetch(event.request)
        .then((response) => {
          if (response.ok) {
            const clone = response.clone();
            caches.open(CACHE_NAME).then((cache) => cache.put(event.request, clone));
          }
          return response;
        })
        .catch(() => cached);
      return cached || network;
    })
  );
});
