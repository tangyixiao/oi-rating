/* Service Worker —— 让网站可以"添加到主屏"并离线打开
 * 策略：
 *   · /api/ 开头的请求一律走网络（数据必须最新，不缓存）
 *   · 其它静态资源：网络优先，失败时用缓存（离线也能打开页面）
 * 改版时把 VERSION 加一，旧缓存会自动清掉。
 */
const VERSION = 'sxyz-rating-v2';   // 2026-10-28 隐藏选手功能：加一，旧缓存自动清掉
const SHELL = ['./', './index.html', './manifest.webmanifest', './icon-192.png', './icon-512.png'];

self.addEventListener('install', e => {
  e.waitUntil(caches.open(VERSION).then(c => c.addAll(SHELL)).then(() => self.skipWaiting()).catch(() => {}));
});

self.addEventListener('activate', e => {
  e.waitUntil(
    caches.keys()
      .then(keys => Promise.all(keys.filter(k => k !== VERSION).map(k => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', e => {
  const url = new URL(e.request.url);
  if (e.request.method !== 'GET') return;
  // 接口：永远走网络
  if (url.pathname.startsWith('/api/')) return;
  // 跨域资源不插手
  if (url.origin !== location.origin) return;

  e.respondWith(
    fetch(e.request)
      .then(res => {
        const copy = res.clone();
        caches.open(VERSION).then(c => c.put(e.request, copy)).catch(() => {});
        return res;
      })
      .catch(() => caches.match(e.request).then(r => r || caches.match('./index.html')))
  );
});
