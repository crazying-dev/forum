// 妖精论坛 Service Worker - 离线缓存静态资源
var CACHE_NAME = 'forum-new-v7';
var CACHE_URLS = [
  '/',
  '/forum',
  '/static/css/main.css?v=11',
  '/static/js/marked.min.js',
  '/static/js/AfterBody.js?v=11',
  '/static/manifest.json',
  '/static/img/favicon.png'
];

// 安装：预缓存核心资源
self.addEventListener('install', function (e) {
  e.waitUntil(
    caches.open(CACHE_NAME).then(function (cache) {
      return cache.addAll(CACHE_URLS).catch(function () {});
    }).then(function () {
      return self.skipWaiting();
    })
  );
});

// 激活：清理旧缓存
self.addEventListener('activate', function (e) {
  e.waitUntil(
    caches.keys().then(function (names) {
      return Promise.all(
        names.filter(function (n) { return n !== CACHE_NAME; })
             .map(function (n) { return caches.delete(n); })
      );
    }).then(function () {
      return self.clients.claim();
    })
  );
});

// 拦截请求：缓存优先，网络回源
self.addEventListener('fetch', function (e) {
  if (e.request.method !== 'GET') return;
  e.respondWith(
    caches.match(e.request).then(function (cached) {
      if (cached) return cached;
      return fetch(e.request).then(function (resp) {
        // 仅缓存同源成功响应
        if (resp.status === 200 && e.request.url.startsWith(self.location.origin)) {
          var respClone = resp.clone();
          caches.open(CACHE_NAME).then(function (cache) {
            cache.put(e.request, respClone).catch(function () {});
          });
        }
        return resp;
      }).catch(function () {
        return caches.match('/');
      });
    })
  );
});
