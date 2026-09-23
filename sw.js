/* 宝宝音乐盒 Service Worker
 * 策略：
 *  - 静态资源（html/js/css/图片）→ 缓存优先 + 后台更新
 *  - API 请求 → 网络优先，失败回退缓存（离线可看已缓存内容）
 *  - 音频代理 → 不缓存（流式，避免占空间）
 */
const CACHE = "baobao-music-v1";
const STATIC_ASSETS = [
  "/player.html",
  "/manifest.json",
  "/icon-192.png",
  "/icon-512.png",
  "/favicon.png"
];

// 安装：预缓存静态资源
self.addEventListener("install", e => {
  e.waitUntil(
    caches.open(CACHE).then(c => c.addAll(STATIC_ASSETS).catch(() => {}))
      .then(() => self.skipWaiting())
  );
});

// 激活：清理旧缓存
self.addEventListener("activate", e => {
  e.waitUntil(
    caches.keys().then(keys =>
      Promise.all(keys.filter(k => k !== CACHE).map(k => caches.delete(k)))
    ).then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", e => {
  const req = e.request;
  const url = new URL(req.url);

  // 只处理同源
  if (url.origin !== location.origin) return;

  // 音频代理：直接放行，不缓存
  if (url.pathname === "/api/proxy") return;

  // API：网络优先，失败回退缓存
  if (url.pathname.startsWith("/api/")) {
    e.respondWith(
      fetch(req).then(res => {
        // 只缓存成功的 GET
        if (req.method === "GET" && res.ok) {
          const clone = res.clone();
          caches.open(CACHE).then(c => c.put(req, clone)).catch(() => {});
        }
        return res;
      }).catch(() => caches.match(req))
    );
    return;
  }

  // 静态资源：缓存优先 + 后台更新
  if (req.method === "GET") {
    e.respondWith(
      caches.match(req).then(cached => {
        const fetchPromise = fetch(req).then(res => {
          if (res.ok) {
            const clone = res.clone();
            caches.open(CACHE).then(c => c.put(req, clone)).catch(() => {});
          }
          return res;
        }).catch(() => cached);
        return cached || fetchPromise;
      })
    );
  }
});
