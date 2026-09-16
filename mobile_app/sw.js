const CACHE_NAME = "nohtus-mobile-shell-v7";
const SHELL_FILES = ["./", "./index.html", "./styles.css?v=3", "./app.js?v=4", "./manifest.json"];

self.addEventListener("install", (event) => {
  // cache.addAll()은 파일 하나라도 그 순간 네트워크가 불안정해서 실패하면
  // install 이벤트 전체가 실패로 처리된다. iOS는 install이 실패한(또는 걸린)
  // 서비스워커가 있으면 그 스코프의 무관한 fetch(로그인 요청 등)까지 응답
  // 없이 멈추는 경우가 있어서, 파일 하나씩 개별 캐싱 + 실패 허용으로 바꿔
  // install이 거의 항상 깨끗하게 끝나게 한다.
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) =>
      Promise.all(
        SHELL_FILES.map((file) =>
          cache.add(file).catch((err) => {
            console.warn("sw install: failed to cache", file, err);
          })
        )
      )
    )
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
  // 국기 이미지(flagcdn.com) 같은 외부 origin 요청은 손대지 않고 브라우저의
  // 기본 네트워크/캐시 처리에 그대로 맡긴다. CORS가 없는 cross-origin
  // 요청을 서비스워커가 가로채서 Cache Storage에 opaque 응답으로 저장했다가
  // 다시 꺼내 쓰면, iOS에서 이미지가 흰 사각형으로 깨져 보이는 문제가 있었다.
  if (url.origin !== self.location.origin) return;
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
