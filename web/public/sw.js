// Hermes 서비스 워커: 앱 셸과 최근에 본 화면(피드에 실린 카드 최대 50장)을 캐시해 오프라인에서도 넘겨 볼 수 있게 한다.
// 스와이프 결과는 페이지가 기기에 쌓아 두었다가 온라인이 되면 보낸다(lib/client.ts).
const VERSION = "hermes-v1";
const SHELL = ["/", "/kept", "/status", "/manifest.webmanifest", "/icon-192.png"];

self.addEventListener("install", (e) => {
  e.waitUntil(caches.open(VERSION).then((c) => c.addAll(SHELL)).then(() => self.skipWaiting()));
});

self.addEventListener("activate", (e) => {
  e.waitUntil(
    caches
      .keys()
      .then((keys) => Promise.all(keys.filter((k) => k !== VERSION).map((k) => caches.delete(k))))
      .then(() => self.clients.claim()),
  );
});

self.addEventListener("fetch", (e) => {
  const req = e.request;
  if (req.method !== "GET") return;
  const url = new URL(req.url);
  if (url.origin !== self.location.origin || url.pathname.startsWith("/api/")) return;

  // 빌드 산출물은 해시가 붙어 바뀌지 않는다: 캐시 우선
  if (url.pathname.startsWith("/_next/static/") || /\.(png|svg|webmanifest)$/.test(url.pathname)) {
    e.respondWith(
      caches.match(req).then(
        (hit) =>
          hit ||
          fetch(req).then((res) => {
            const copy = res.clone();
            caches.open(VERSION).then((c) => c.put(req, copy));
            return res;
          }),
      ),
    );
    return;
  }

  // 화면과 RSC 요청: 네트워크 우선, 실패하면 캐시
  e.respondWith(
    fetch(req)
      .then((res) => {
        if (res.ok) {
          const copy = res.clone();
          caches.open(VERSION).then((c) => c.put(req, copy));
        }
        return res;
      })
      .catch(() => caches.match(req).then((hit) => hit || caches.match("/"))),
  );
});
