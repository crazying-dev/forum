/* 妖精论坛 Service Worker —— 仅满足 PWA 可安装条件，不做离线缓存 */
/* 升级时修改此版本号，配合路由侧 Cache-Control: no-cache 保证尽快接管 */
const SW_VERSION = '1.0.0';

self.addEventListener('install', (event) => {
  // 新版本立即激活，不等旧页面关闭
  self.skipWaiting();
});

self.addEventListener('activate', (event) => {
  event.waitUntil(self.clients.claim());
});

// 空 fetch 监听：存在即满足浏览器安装条件；不 respondWith，请求走默认网络，行为与未注册时一致
self.addEventListener('fetch', () => {});
