/* 妖精论坛 Service Worker —— 仅满足 PWA 可安装条件，不做离线缓存 */
/* 版本号由环境变量 SW_VERSION 接管（见 api/config.py），部署时修改即可强制更新 */
const SW_VERSION = '__SW_VERSION__';

self.addEventListener('install', (event) => {
  // 新版本立即激活，不等旧页面关闭
  self.skipWaiting();
});

self.addEventListener('activate', (event) => {
  event.waitUntil(self.clients.claim());
});

// 空 fetch 监听：存在即满足浏览器安装条件；不 respondWith，请求走默认网络，行为与未注册时一致
self.addEventListener('fetch', () => {});
