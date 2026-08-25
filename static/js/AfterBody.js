/* 妖精论坛（forum-new）前端主脚本 v2：含全部功能（评论楼中楼/资料编辑/关注/分享/编辑器/懒加载/复制/菜单/彩蛋） */
(function () {
  'use strict';

  // ── API 封装（含同请求去重 / GET 短暂缓存）──────────────
  // 相同 (method, url, body) 请求合并为一次 in-flight Promise。
  // 对 GET：成功响应再内存缓存 800ms，防止极短时间内重复请求（比如换一批点击、渲染并发）。
  var _pendingFetches = new Map();   // dedup key -> in-flight Promise
  var _cachedFetches = new Map();    // dedup key -> {at, value}  (仅 GET 成功)
  var _GET_CACHE_TTL_MS = 800;
  var _dedupWarnedMissing = false;

  function _dedupKey(method, url, body) {
    var m = (method || 'GET').toUpperCase();
    // body 可能是对象（apiFetch 内部 o.body）或字符串（调用方自己拼的都统一处理）
    var bodyStr;
    if (body === undefined || body === null) bodyStr = '';
    else if (typeof body === 'string') bodyStr = body;
    else {
      try { bodyStr = JSON.stringify(body); } catch (_) { bodyStr = String(body); }
    }
    return m + '|' + url + '|' + bodyStr;
  }

  async function apiFetch(url, opts) {
    var o = opts || {};
    var method = (o.method || 'GET').toUpperCase();
    var key = _dedupKey(method, url, o.body);

    // ① GET 短暂内存缓存命中 → 直接返回（800ms 窗口内，同 URL 不重复请求）
    if (method === 'GET') {
      var cached = _cachedFetches.get(key);
      if (cached && (Date.now() - cached.at) <= _GET_CACHE_TTL_MS) {
        return cached.value;
      } else if (cached) {
        _cachedFetches.delete(key);
      }
    }
    // ② 正在飞的相同请求 → 复用 Promise，不重复发请求
    if (_pendingFetches.has(key)) {
      return _pendingFetches.get(key);
    }

    var headers = Object.assign({ 'Content-Type': 'application/json' }, o.headers || {});
    var promise = (async function () {
      var resp = await fetch(url, {
        method: method,
        headers: headers,
        credentials: 'same-origin',
        body: o.body ? JSON.stringify(o.body) : undefined
      });
      if (resp.status === 401) {
        if (!o.noAuthRedirect && !/\/(login|register|auth|reset-password)$/.test(location.pathname)) {
          location.href = '/auth';
          return null;
        }
      }
      var data = null;
      try { data = await resp.json(); } catch (e) {}
      if (!data) throw new Error('响应解析失败');
      // GET 成功 → 写缓存（TTL 800ms，防刷）
      if (method === 'GET' && data) {
        _cachedFetches.set(key, { at: Date.now(), value: data });
      }
      return data;
    })();
    // 结束后清 in-flight
    promise.then(
      function () { _pendingFetches.delete(key); },
      function () { _pendingFetches.delete(key); }
    );
    _pendingFetches.set(key, promise);
    return promise;
  }

  // ── 工具 ────────────────────────────────
  function esc(s) {
    return String(s == null ? '' : s)
      .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
  }
  function avatarHtml(url, cls) {
    cls = cls || 'avatar-sm';
    // 头像 img 不阻塞 DOM 初始加载：真实 URL 放到 data-src，加上 loading=lazy / decoding=async。
    // 注入逻辑：1) DOMContentLoaded 全量 resolve；2) 每次渲染列表后手动调用 resolveAvatarDeferred()。
    if (url) return '<span class="' + cls + '"><img data-src="' + esc(url) + '" src="data:image/gif;base64,R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7" loading="lazy" decoding="async" alt=""></span>';
    return '<span class="' + cls + '"><i class="fa fa-user"></i></span>';
  }

  // 把 scope 容器内所有 <img data-src="..."> 的真实 URL 注入到 src，触发异步加载。
  // scope 默认 document（DOM 初启后全量），传具体容器只处理新渲染出的那批（更高效）。
  function resolveAvatarDeferred(scope) {
    try {
      var root = scope && scope.querySelectorAll ? scope : document;
      var imgs = root.querySelectorAll('img[data-src]');
      for (var i = 0; i < imgs.length; i++) {
        var img = imgs[i];
        var realSrc = img.getAttribute('data-src');
        if (realSrc && img.getAttribute('src') !== realSrc) {
          img.onload = (function (el) { return function () { el.removeAttribute('data-src'); }; })(img);
          img.onerror = (function (el) { return function () { el.removeAttribute('data-src'); }; })(img);
          img.src = realSrc;
        } else if (img.getAttribute('src') === realSrc) {
          img.removeAttribute('data-src');
        }
      }
    } catch (e) {}
  }
  function fmtTime(t) {
    if (!t) return '';
    var d = new Date(t.indexOf('T') >= 0 ? t : t.replace(' ', 'T') + (t.length >= 19 ? '+08:00' : ''));
    if (isNaN(d.getTime())) return t;
    var now = new Date();
    var diff = (now - d) / 1000;
    if (diff < 60) return '刚刚';
    if (diff < 3600) return Math.floor(diff / 60) + ' 分钟前';
    if (diff < 86400) return Math.floor(diff / 3600) + ' 小时前';
    var pad = function (n) { return n < 10 ? '0' + n : '' + n; };
    return d.getFullYear() + '-' + pad(d.getMonth() + 1) + '-' + pad(d.getDate()) + ' ' + pad(d.getHours()) + ':' + pad(d.getMinutes());
  }
  function el(id) { return document.getElementById(id); }

  // toast 提示
  function toast(msg) {
    var t = el('toast');
    if (!t) return;
    t.textContent = msg;
    t.classList.add('show');
    clearTimeout(t._timer);
    t._timer = setTimeout(function () { t.classList.remove('show'); }, 2200);
  }

  // ── 当前用户状态 ──
  var currentUser = null;

  // ── 主题（亮/暗/默认 + localStorage）──
  function setTheme(v) {
    var root = document.documentElement;
    if (v === 'day') { root.classList.remove('night-mode'); try { localStorage.setItem('forum-theme', 'day'); } catch (e) {} }
    else if (v === 'night') { root.classList.add('night-mode'); try { localStorage.setItem('forum-theme', 'night'); } catch (e) {} }
    else { try { localStorage.removeItem('forum-theme'); } catch (e) {} var h = new Date().getHours(); if (h < 6 || h >= 18) root.classList.add('night-mode'); else root.classList.remove('night-mode'); }
  }

  // ── 认证状态 → header ──
  async function initAuth() {
    var navUser = el('navUser');
    if (!navUser) return;
    try {
      var data = await apiFetch('/api/user/info', { noAuthRedirect: true });
      if (data && data.success) {
        currentUser = data.user;
        var u = data.user;
        navUser.innerHTML =
          '<a href="/users/' + esc(u.id) + '" class="user-chip">' +
          avatarHtml(u.avatar, 'avatar') +
          '<span class="user-chip-name">' + esc(u.name) + '</span>' +
          '</a>';
        // navUser 是异步填充的，必须在写入后立即解析 data-src，否则头像不显示
        resolveAvatarDeferred(navUser);
        var li = el('logoutItem'), ml = el('mobileLogout');
        if (li) li.style.display = '';
        if (ml) ml.style.display = '';
      }
    } catch (e) {
      navUser.innerHTML = '<a href="/auth" class="nav-login">登录</a>';
    }
  }

  // ── 设置菜单 / 移动菜单 / 彩蛋 ──
  function initMenus() {
    // 设置下拉
    var settingBtn = el('settingBtn'), dropdown = el('settingDropdown');
    if (settingBtn && dropdown) {
      settingBtn.addEventListener('click', function (e) {
        e.stopPropagation();
        dropdown.classList.toggle('open');
      });
      document.addEventListener('click', function () { dropdown.classList.remove('open'); });
      dropdown.addEventListener('click', function (e) { e.stopPropagation(); });
      dropdown.querySelectorAll('[data-theme]').forEach(function (b) {
        b.addEventListener('click', function () { setTheme(b.getAttribute('data-theme')); dropdown.classList.remove('open'); });
      });
    }
    // 移动菜单
    var toggle = el('menuToggle'), mMenu = el('mobileMenu');
    if (toggle && mMenu) {
      toggle.addEventListener('click', function () { mMenu.classList.toggle('open'); });
      mMenu.querySelectorAll('[data-theme]').forEach(function (b) {
        b.addEventListener('click', function () { setTheme(b.getAttribute('data-theme')); mMenu.classList.remove('open'); });
      });
    }
    // 退出登录（设置菜单 + 移动菜单）
    [el('logoutItem'), el('mobileLogout')].forEach(function (b) {
      if (!b) return;
      b.addEventListener('click', async function () {
        await apiFetch('/api/user/logout', { method: 'POST' });
        location.href = '/';
      });
    });
    // 彩蛋
    [el('eggBtn'), el('mobileEggBtn')].forEach(function (b) {
      if (!b) return;
      b.addEventListener('click', async function () {
        try {
          var d = await apiFetch('/Easter-Egg');
          if (d && (d.Name || d.Text)) toast('🎁 ' + (d.Name || '彩蛋') + (d.Text ? '：' + d.Text : ''));
          else toast('🎁 彩蛋为空');
        } catch (e) { toast('彩蛋获取失败'); }
      });
    });
  }

  // ── 侧边栏世界频道：拖拽调宽 / 收起 ──
  function initWorldPanel() {
    var panel = el('worldPanel');
    if (!panel) return;
    var resizer = el('worldResizer');
    var collapseBtn = el('worldCollapseBtn');
    var WIDTH_KEY = 'forum_world_width';
    var COLLAPSE_KEY = 'forum_world_collapsed';
    function applyCollapsed() {
      var collapsed = false;
      try { collapsed = localStorage.getItem(COLLAPSE_KEY) === '1'; } catch (e) {}
      if (window.innerWidth <= 900 && !localStorage.getItem(COLLAPSE_KEY)) collapsed = true;
      panel.classList.toggle('collapsed', collapsed);
      if (collapseBtn) collapseBtn.innerHTML = collapsed ? '<i class="fa fa-angle-left"></i>' : '<i class="fa fa-angle-right"></i>';
      return collapsed;
    }
    // 刷新时若上次是收起状态：先跳过过渡动画，避免"展开→收缩"闪现
    panel.classList.add('no-anim');
    applyWidth();
    applyCollapsed();
    requestAnimationFrame(function () {
      requestAnimationFrame(function () { panel.classList.remove('no-anim'); });
    });
    function applyWidth() {
      var w = null;
      try { w = parseInt(localStorage.getItem(WIDTH_KEY), 10); } catch (e) {}
      if (w && w >= 240 && w <= 560) {
        panel.style.width = w + 'px';
        panel.style.setProperty('--world-width', w + 'px');
      }
    }
    if (collapseBtn) {
      collapseBtn.addEventListener('click', function () {
        var collapsed = !panel.classList.contains('collapsed');
        panel.classList.toggle('collapsed', collapsed);
        try { localStorage.setItem(COLLAPSE_KEY, collapsed ? '1' : '0'); } catch (e) {}
        collapseBtn.innerHTML = collapsed ? '<i class="fa fa-angle-left"></i>' : '<i class="fa fa-angle-right"></i>';
      });
    }
    if (resizer) {
      resizer.addEventListener('mousedown', function (e) {
        e.preventDefault();
        var startX = e.clientX;
        var startW = panel.offsetWidth;
        function onMove(ev) {
          var w = startW + (startX - ev.clientX);
          w = Math.max(240, Math.min(560, w));
          panel.style.width = w + 'px';
          panel.style.setProperty('--world-width', w + 'px');
        }
        function onUp() {
          document.removeEventListener('mousemove', onMove);
          document.removeEventListener('mouseup', onUp);
          try { localStorage.setItem(WIDTH_KEY, String(panel.offsetWidth)); } catch (e) {}
        }
        document.addEventListener('mousemove', onMove);
        document.addEventListener('mouseup', onUp);
      });
    }
  }

  // ── 世界频道 HTTP 轮询（不再使用 WebSocket 长连接）──
  var wsRetry = 0;
  var worldMessages = [];
  var myUserId = null;
  var worldPollTimer = null;

  function worldStatus(text, cls) {
    var s = el('worldStatus');
    if (!s) return;
    s.textContent = text;
    s.className = 'world-status' + (cls ? ' ' + cls : '');
  }

  function renderWorldMessages() {
    var dom = el('worldMessages');
    if (!dom) return;
    if (!worldMessages.length) {
      dom.innerHTML = '<div class="world-empty">暂无消息，快来抢沙发~</div>';
      return;
    }
    var html = '';
    for (var i = 0; i < worldMessages.length; i++) {
      var m = worldMessages[i];
      var mine = myUserId && m.sender_id === myUserId;
      html +=
        '<div class="world-msg' + (mine ? ' world-msg-mine' : '') + '">' +
        avatarHtml(m.sender_avatar) +
        '<div class="world-msg-body">' +
        '<div class="world-msg-name">' + esc(m.sender_name) + '</div>' +
        '<div class="world-msg-content">' + esc(m.content) + '</div>' +
        '<div class="world-msg-time">' + fmtTime(m.created_at) + '</div>' +
        '</div></div>';
    }
    dom.innerHTML = html;
    resolveAvatarDeferred(dom);
    dom.scrollTop = dom.scrollHeight;
  }

  function connectWorld() {
    var panel = el('worldPanel');
    if (!panel) return;
    if (worldPollTimer) { clearTimeout(worldPollTimer); worldPollTimer = null; }
    worldStatus('连接中…', '');

    // 判断面板"是否显示给用户"：收起 / 不渲染都视为不显示，这两种情况不发请求（节省流量 + 减少后台无效轮询）
    function isPanelShown() {
      if (!panel) return false;
      var style = window.getComputedStyle(panel);
      if (style.display === 'none' || style.visibility === 'hidden') return false;
      if (panel.classList.contains('collapsed')) return false;
      return true;
    }

    // 3 条件全部满足才允许真的发起 /api/world/ALL 请求：
    //   ① 面板当前显示（未收起/未隐藏） ② 页面可见（非后台 tab） ③ 世界面板功能仍存在
    function canPoll() {
      if (!el('worldPanel')) return false;
      if (document.hidden) return false;
      return isPanelShown();
    }

    function poll() {
      // —— 需求 2：不显示时不请求 ——
      if (!isPanelShown()) {
        worldPollTimer = setTimeout(poll, 1500);   // 收起状态下仍低频探测（1.5s）等用户展开
        return;
      }
      // —— 需求 3：页面切后台（document.hidden）时暂停，等 visibilitychange 立刻恢复 ——
      if (document.hidden) {
        worldPollTimer = null;   // 不 set timeout，完全停住
        return;
      }
      apiFetch('/api/world/ALL', { noAuthRedirect: true })
        .then(function (messages) {
          if (Array.isArray(messages)) {
            worldMessages = messages.slice(0, 200);
            renderWorldMessages();
            worldStatus('在线', 'online');
            wsRetry = 0;
            // 只有当前仍允许轮询才排下一次；否则由可见性/展开事件触发重新 poll
            if (canPoll()) worldPollTimer = setTimeout(poll, 3000);
            else worldPollTimer = null;
          } else {
            worldStatus('加载失败', 'offline');
            scheduleRetry();
          }
        })
        .catch(function () {
          worldStatus('连接失败', 'offline');
          scheduleRetry();
        });
    }
    function scheduleRetry() {
      if (!canPoll()) { worldPollTimer = null; return; }
      var delay = Math.min(30000, 3000 * Math.pow(2, Math.min(wsRetry, 4)));
      wsRetry++;
      worldPollTimer = setTimeout(poll, delay);
    }

    // —— 页面可见性监听：切后台立刻停、切前台立刻抓一次 ——
    function onVisibility() {
      if (document.hidden) {
        if (worldPollTimer) { clearTimeout(worldPollTimer); worldPollTimer = null; }
      } else {
        // 回到前台且面板显示 → 立刻 poll 一次；否则保持等待
        if (isPanelShown()) poll();
      }
    }
    // 只注册一次（单例监听，避免 connectWorld 被重复调用时叠加）
    if (!connectWorld._visibilityBound) {
      document.addEventListener('visibilitychange', onVisibility, { passive: true });
      connectWorld._visibilityBound = true;
    }

    // —— 面板"展开/收起"按钮点击后同步：收起时清 timeout，展开时立刻 poll 一次 ——
    function afterTogglePanel() {
      if (isPanelShown() && !document.hidden) {
        if (worldPollTimer) { clearTimeout(worldPollTimer); worldPollTimer = null; }
        poll();
      }
    }
    if (!connectWorld._toggleBound) {
      document.addEventListener('click', function (e) {
        var t = e.target;
        while (t && t !== document) {
          if (t.classList && (t.classList.contains('world-collapse') || t.classList.contains('world-float-btn'))) {
            // 点击后会切换 collapsed 类，用 0 延迟让 DOM 类名先更新
            setTimeout(afterTogglePanel, 0);
            return;
          }
          t = t.parentNode;
        }
      }, { passive: true });
      connectWorld._toggleBound = true;
    }

    poll();
  }

  function sendWorldMessage(content) {
    if (!content) return;
    if (!currentUser) { location.href = '/auth'; return; }
    apiFetch('/api/world/Send', { method: 'POST', body: { content: content } })
      .then(function (d) { if (d && !d.success && d.message) toast(d.message); })
      .catch(function () {});
  }

  function initWorldChat() {
    var input = el('worldInput');
    var sendBtn = el('worldSendBtn');
    if (!input || !sendBtn) return;
    sendBtn.addEventListener('click', function () {
      sendWorldMessage(input.value.trim());
      input.value = '';
    });
    input.addEventListener('keydown', function (e) {
      if (e.key === 'Enter') {
        sendWorldMessage(input.value.trim());
        input.value = '';
      }
    });
    if (currentUser) myUserId = currentUser.id;
  }

  // ── 搜索框 ──
  function initSearchBox() {
    var input = el('searchInput');
    var btn = el('searchBtn');
    function go() {
      var k = (input.value || '').trim();
      if (k) location.href = '/search?k=' + encodeURIComponent(k);
    }
    if (btn) btn.addEventListener('click', go);
    if (input) input.addEventListener('keydown', function (e) { if (e.key === 'Enter') go(); });
    if (location.pathname === '/search' && input) {
      var params = new URLSearchParams(location.search);
      var k = params.get('k') || '';
      if (k) input.value = k;
    }
  }

  // ── 页面入口（Part 2 会扩展）──
  window.__yoyoApp = {
    apiFetch: apiFetch,
    esc: esc,
    el: el,
    toast: toast,
    fmtTime: fmtTime,
    avatarHtml: avatarHtml,
    resolveAvatarDeferred: resolveAvatarDeferred,
    setTheme: setTheme,
    get currentUser() { return currentUser; },
    initAuth: initAuth,
    initMenus: initMenus,
    initWorldPanel: initWorldPanel,
    connectWorld: connectWorld,
    initWorldChat: initWorldChat,
    initSearchBox: initSearchBox
  };
})();

/* ══════════ 页面渲染（Part 2）══════════ */
(function () {
  'use strict';
  var app = window.__yoyoApp;
  var apiFetch = app.apiFetch, esc = app.esc, el = app.el, toast = app.toast, fmtTime = app.fmtTime, avatarHtml = app.avatarHtml, resolveAvatarDeferred = app.resolveAvatarDeferred;

  // ── 帖子分类汉化映射 ──
  // 除 V2 现有分类外，兼容 V1 存量帖子的英文分类（talk/share/creative 等），保证统一显示中文
  var CATEGORY_MAP = {
    'general': '综合',
    '叶羽': '叶羽',
    '创意': '创意',
    '求助': '求助',
    // V1 存量分类兼容
    'talk': '闲聊',
    'question': '求助',
    'share': '分享',
    'creative': '创作'
  };
  function categoryLabel(c) {
    var key = c || 'general';
    return CATEGORY_MAP[key] || key;
  }

  // ── Markdown 渲染（使用 marked.js）──
  // 配置：headerIds 关闭避免 id 冲突；mangle 关闭避免邮箱被转义；
  // 默认 marked 已对原始 HTML 做转义，这里再显式关闭内联 HTML 解析。
  if (typeof marked !== 'undefined') {
    marked.setOptions({
      headerIds: false,
      mangle: false,
      breaks: true,
      gfm: true
    });
  }
  function renderMarkdown(text) {
    if (!text) return '';
    if (typeof marked !== 'undefined' && marked.parse) {
      try { return marked.parse(text); } catch (e) {}
    }
    // 兜底：纯文本展示
    return '<p>' + esc(text) + '</p>';
  }

  function postItemHtml(p) {
    return (
      '<div class="post-item" data-pid="' + esc(p.id) + '" data-uid="' + esc(p.user_id) + '" data-post-link="/post/' + esc(p.id) + '">' +
      '<a class="post-item-title" href="/post/' + esc(p.id) + '">' + esc(p.title) + '</a>' +
      '<div class="post-item-summary">' + esc(p.summary || '') + '</div>' +
      '<div class="post-item-meta">' +
      '<span class="tag">' + esc(categoryLabel(p.category)) + '</span>' +
      '<span>' + avatarHtml(p.user_avatar) + ' <a class="link-user" href="/users/' + esc(p.user_id) + '">' + esc(p.user_name) + '</a></span>' +
      '<span><i class="fa fa-thumbs-o-up"></i> ' + (p.likes || 0) + '</span>' +
      '<span><i class="fa fa-eye"></i> ' + (p.views || 0) + '</span>' +
      '<span>' + fmtTime(p.created_at) + '</span>' +
      '</div></div>'
    );
  }

  // ── 首页 ──
  function initHome() {
    var list = el('homePostList');
    if (!list) return;
    // 排序模式：random（随机推荐）/ time（时间顺序）/ comprehensive（综合排序）
    var sortMode = 'random';
    var sortLabels = { random: '随机推荐', time: '时间顺序', comprehensive: '综合排序' };
    var sortIcons = { random: 'fa-random', time: 'fa-clock-o', comprehensive: 'fa-fire' };
    var sortUrls = {
      random: '/api/posts/random?limit=200',
      time: '/api/posts?sort=time&page_size=100',
      comprehensive: '/api/posts?sort=comprehensive&page_size=100'
    };
    var homeRefreshLocked = false;
    function loadHome() {
      list.innerHTML = '<div class="empty">加载中...</div>';
      apiFetch(sortUrls[sortMode]).then(function (d) {
        if (!d || !d.success) { list.innerHTML = '<div class="empty">加载失败</div>'; return; }
        var posts = d.posts || [];
        if (!posts.length) { list.innerHTML = '<div class="empty">暂无帖子</div>'; return; }
        list.innerHTML = posts.map(postItemHtml).join('');
        resolveAvatarDeferred(list);
      }).catch(function () { list.innerHTML = '<div class="empty">加载失败</div>'; });
    }
    var refresh = el('homeRefreshBtn');
    if (refresh) refresh.addEventListener('click', function () {
      if (homeRefreshLocked) return;
      homeRefreshLocked = true;
      refresh.classList.add('disabled');
      loadHome();
      setTimeout(function () {
        homeRefreshLocked = false;
        refresh.classList.remove('disabled');
      }, 5000);
    });
    // 排序下拉框：点击标题展开「随机推荐 / 时间顺序 / 综合排序」
    var sortToggle = el('homeSortToggle');
    var sortMenu = el('homeSortMenu');
    var sortLabel = el('homeSortLabel');
    var sortIcon = el('homeSortIcon');
    if (sortToggle && sortMenu) {
      sortToggle.addEventListener('click', function (e) {
        e.stopPropagation();
        sortMenu.classList.toggle('open');
      });
      sortMenu.querySelectorAll('.home-sort-item').forEach(function (b) {
        b.addEventListener('click', function () {
          sortMode = b.getAttribute('data-sort') || 'random';
          sortMenu.querySelectorAll('.home-sort-item').forEach(function (x) { x.classList.remove('active'); });
          b.classList.add('active');
          if (sortLabel) sortLabel.textContent = sortLabels[sortMode] || sortLabels.random;
          if (sortIcon) {
            sortIcon.className = 'fa ' + (sortIcons[sortMode] || sortIcons.random);
          }
          sortMenu.classList.remove('open');
          loadHome();
        });
      });
      document.addEventListener('click', function () { sortMenu.classList.remove('open'); });
    }
    loadHome();
    // 首页「我的收藏」可折叠
    var favSection = el('homeFavorites');
    var favToggle = el('homeFavToggle');
    if (favToggle) favToggle.addEventListener('click', function () {
      var body = el('homeFavoritesBody');
      if (!body) return;
      var collapsed = body.style.display === 'none';
      body.style.display = collapsed ? '' : 'none';
      favToggle.classList.toggle('collapsed', !collapsed);
      favToggle.innerHTML = collapsed ? '<i class="fa fa-angle-up"></i> 收起' : '<i class="fa fa-angle-down"></i> 展开';
    });
    if (favSection && app.currentUser) {
      apiFetch('/api/user/' + app.currentUser.id + '/favorites').then(function (d) {
        if (d && d.success && (d.posts || []).length) {
          favSection.style.display = '';
          var favList = el('homeFavoritesList');
          favList.innerHTML = d.posts.map(postItemHtml).join('');
          resolveAvatarDeferred(favList);
        }
      }).catch(function () {});
    }
  }

  // ── 论坛列表 ──
  function initForum() {
    var list = el('postList');
    if (!list) return;
    var page = 1, category = '', hasMore = true;
    function load(reset) {
      if (reset) { page = 1; hasMore = true; list.innerHTML = '<div class="empty">加载中...</div>'; }
      var url = '/api/posts?page=' + page + '&page_size=20' + (category ? '&category=' + encodeURIComponent(category) : '');
      apiFetch(url).then(function (d) {
        if (!d || !d.success) return;
        var posts = d.posts || [];
        if (reset) list.innerHTML = posts.map(postItemHtml).join('');
        else list.innerHTML += posts.map(postItemHtml).join('');
        resolveAvatarDeferred(list);
        hasMore = posts.length >= 20;
        el('loadMore').style.display = hasMore ? '' : 'none';
        if (!posts.length && reset) list.innerHTML = '<div class="empty">暂无帖子</div>';
      }).catch(function () { list.innerHTML = '<div class="empty">加载失败</div>'; });
    }
    document.querySelectorAll('#categoryTabs .tab').forEach(function (t) {
      t.addEventListener('click', function () {
        document.querySelectorAll('#categoryTabs .tab').forEach(function (x) { x.classList.remove('active'); });
        t.classList.add('active');
        category = t.getAttribute('data-category');
        load(true);
      });
    });
    var moreBtn = el('loadMoreBtn');
    if (moreBtn) moreBtn.addEventListener('click', function () { page++; load(false); });
    load(true);
  }

  // ── 内容后处理：懒加载 + 复制代码按钮 ──
  function enhanceContent(container) {
    if (!container) return;
    // 图片懒加载（原生 loading=lazy）
    container.querySelectorAll('img').forEach(function (img) {
      if (!img.getAttribute('loading')) img.setAttribute('loading', 'lazy');
    });
    // 代码块复制按钮
    container.querySelectorAll('pre code, pre').forEach(function (pre) {
      if (pre.closest('.code-copy-wrap')) return;
      var wrap = document.createElement('div');
      wrap.className = 'code-copy-wrap';
      var btn = document.createElement('button');
      btn.className = 'code-copy-btn';
      btn.textContent = '复制';
      btn.addEventListener('click', function () {
        var text = pre.innerText || pre.textContent || '';
        (navigator.clipboard ? navigator.clipboard.writeText(text) : Promise.reject())
          .then(function () { toast('已复制'); })
          .catch(function () {
            var ta = document.createElement('textarea');
            ta.value = text;
            document.body.appendChild(ta);
            ta.select();
            try { document.execCommand('copy'); toast('已复制'); } catch (e) { toast('复制失败'); }
            document.body.removeChild(ta);
          });
      });
      pre.parentNode.insertBefore(wrap, pre);
      wrap.appendChild(pre);
      wrap.appendChild(btn);
    });
  }

  // ── 评论楼中楼：按 parent_id 分组渲染 ──
  function renderComments(comments) {
    var list = el('commentList');
    if (!list) return;
    if (!comments.length) { list.innerHTML = '<div class="empty">暂无评论</div>'; return; }
    var tops = [], children = {};
    comments.forEach(function (c) {
      if (c.parent_id && comments.some(function (x) { return x.id === c.parent_id; })) {
        (children[c.parent_id] = children[c.parent_id] || []).push(c);
      } else {
        tops.push(c);
      }
    });
    function commentHtml(c, isChild) {
      var html =
        '<div class="comment-item' + (isChild ? ' comment-child' : '') + '" data-cid="' + esc(c.id) + '"' +
        ' data-cuid="' + esc(c.user_id) + '" data-post-link="' + esc(location.pathname + location.search) + '">' +
        avatarHtml(c.user_avatar) +
        '<div class="comment-body">' +
        '<div class="comment-head"><a href="/users/' + esc(c.user_id) + '">' + esc(c.user_name) + '</a>' +
        (c.parent_id ? ' <span class="comment-reply-to">回复</span>' : '') +
        ' · ' + fmtTime(c.created_at) + '</div>' +
        '<div class="comment-content">' + esc(c.content) + '</div>' +
        '<div class="comment-actions">' +
        '<button class="comment-reply" data-reply="' + esc(c.id) + ':' + esc(c.user_name) + '">回复</button>' +
        (app.currentUser && app.currentUser.id === c.user_id
          ? '<button class="comment-reply" data-del-comment="' + esc(c.id) + '">删除</button>' : '') +
        '</div>' +
        '</div></div>';
      var kids = children[c.id] || [];
      if (kids.length) {
        html += '<div class="comment-children" data-parent="' + esc(c.id) + '">' +
          kids.map(function (k) { return commentHtml(k, true); }).join('') +
          '</div>';
        html += '<button class="comment-fold" data-fold="' + esc(c.id) + '">收起回复</button>';
      }
      return html;
    }
    list.innerHTML = tops.map(function (c) { return commentHtml(c, false); }).join('');
    resolveAvatarDeferred(list);
    el('commentCount').textContent = '(' + comments.length + ')';
    // 若从个人主页带 #comment-<id> 跳转而来：滚动定位到该评论并高亮
    var h = location.hash || '';
    if (h.indexOf('#comment-') === 0) {
      var target = list.querySelector('[data-cid="' + h.slice(9) + '"]');
      if (target) {
        setTimeout(function () {
          target.scrollIntoView({ behavior: 'smooth', block: 'center' });
          target.classList.add('highlight-comment');
        }, 120);
      }
    }
  }

  // ── 帖子详情 ──
  var replyTarget = null; // { id, name }

  function initPostDetail() {
    var card = el('postCard');
    if (!card) return;
    var m = location.pathname.match(/^\/post\/([^\/]+)/);
    var postId = m ? decodeURIComponent(m[1]) : '';
    if (!postId) return;

    apiFetch('/api/posts/' + encodeURIComponent(postId)).then(function (d) {
      if (!d || !d.success) { card.innerHTML = '<div class="empty">帖子不存在</div>'; return; }
      var p = d.post;
      var isAuthor = app.currentUser && app.currentUser.id === p.user_id;
      card.innerHTML =
        '<h1 class="post-detail-title">' + esc(p.title) + '</h1>' +
        '<div class="post-detail-meta">' +
        avatarHtml(p.user_avatar, 'avatar-sm') +
        '<a class="link-user" href="/users/' + esc(p.user_id) + '">' + esc(p.user_name) + '</a>' +
        (app.currentUser && !isAuthor ? '<button class="btn btn-sm btn-outline" id="followAuthorBtn">关注</button>' : '') +
        '<span class="tag">' + esc(categoryLabel(p.category)) + '</span>' +
        '<span><i class="fa fa-eye"></i> ' + (p.views || 0) + '</span>' +
        '<span><i class="fa fa-thumbs-o-up"></i> ' + (p.likes || 0) + '</span>' +
        '<span>' + fmtTime(p.created_at) + '</span>' +
        '</div>' +
        '<div class="post-detail-content markdown-body">' + renderMarkdown(p.content) + '</div>' +
        '<div class="post-actions">' +
        '<button class="btn btn-sm action-btn" id="likeBtn"><i class="fa fa-thumbs-o-up"></i> 点赞 <span id="likeCount">' + (p.likes || 0) + '</span></button>' +
        '<button class="btn btn-sm action-btn" id="favBtn"><i class="fa fa-bookmark-o"></i> 收藏</button>' +
        '<button class="btn btn-sm action-btn" id="shareBtn"><i class="fa fa-share-alt"></i> 分享</button>' +
        '<button class="btn btn-sm btn-outline action-btn" id="reportBtn"><i class="fa fa-flag-o"></i> 举报</button>' +
        (isAuthor ? '<button class="btn btn-sm btn-outline action-btn" id="delBtn"><i class="fa fa-trash-o"></i> 删除</button>' : '') +
        '</div>';
      if (d.liked) el('likeBtn').classList.add('liked');
      el('favBtn').textContent = d.favorited ? '已收藏' : '收藏';
      resolveAvatarDeferred(card);
      enhanceContent(card.querySelector('.post-detail-content'));
      renderComments(d.comments || []);
      bindDetailActions(postId, p.user_id);
    }).catch(function () { card.innerHTML = '<div class="empty">加载失败</div>'; });
  }

  function bindDetailActions(postId, authorId) {
    var likeBtn = el('likeBtn'), favBtn = el('favBtn'), reportBtn = el('reportBtn'), delBtn = el('delBtn'), shareBtn = el('shareBtn');
    var followBtn = el('followAuthorBtn');
    var commentList = el('commentList');
    var commentContent = el('commentContent');
    function needLogin() {
      if (!app.currentUser) { location.href = '/auth'; return true; }
      return false;
    }
    if (likeBtn) likeBtn.addEventListener('click', function () {
      if (needLogin()) return;
      apiFetch('/api/posts/' + postId + '/like', { method: 'POST' }).then(function (d) {
        if (!d) return;
        likeBtn.classList.toggle('liked', d.liked);
        el('likeCount').textContent = d.likes;
      });
    });
    if (favBtn) favBtn.addEventListener('click', function () {
      if (needLogin()) return;
      apiFetch('/api/posts/' + postId + '/favorite', { method: 'POST' }).then(function (d) {
        if (d) favBtn.textContent = d.favorited ? '已收藏' : '收藏';
      });
    });
    if (shareBtn) shareBtn.addEventListener('click', function () {
      var url = location.href;
      (navigator.clipboard ? navigator.clipboard.writeText(url) : Promise.reject())
        .then(function () { toast('链接已复制'); })
        .catch(function () { toast('当前浏览器不支持一键复制'); });
    });
    if (followBtn && authorId) {
      // 初始状态
      apiFetch('/api/user/' + encodeURIComponent(authorId)).then(function (d) {
        if (d && d.success && followBtn) followBtn.textContent = (d.user && d.user.is_following) ? '已关注' : '关注';
      }).catch(function () {});
      followBtn.addEventListener('click', function () {
        if (needLogin()) return;
        apiFetch('/api/user/' + encodeURIComponent(authorId) + '/follow', { method: 'POST' }).then(function (r) {
          if (r) { followBtn.textContent = r.following ? '已关注' : '关注'; toast(r.following ? '已关注作者' : '已取消关注'); }
        });
      });
    }
    if (reportBtn) reportBtn.addEventListener('click', function () {
      if (needLogin()) return;
      openReportModal('post', postId);
    });
    if (delBtn) delBtn.addEventListener('click', function () {
      if (!confirm('确定删除该帖子？')) return;
      apiFetch('/api/posts/' + postId + '/delete', { method: 'POST' }).then(function (d) {
        if (d && d.success) location.href = '/forum';
        else if (d) toast(d.message || '删除失败');
      });
    });
    // 评论：回复 / 删除 / 折叠
    if (commentList) commentList.addEventListener('click', function (e) {
      var replyBtn = e.target.closest('[data-reply]');
      var delBtn2 = e.target.closest('[data-del-comment]');
      var foldBtn = e.target.closest('[data-fold]');
      if (replyBtn) {
        var parts = replyBtn.getAttribute('data-reply').split(':');
        replyTarget = { id: parts[0], name: parts.slice(1).join(':') };
        var bar = el('replyBar');
        if (bar) bar.style.display = '';
        var hint = el('replyHint');
        if (hint) hint.textContent = '回复 @' + replyTarget.name + '：';
        commentContent.focus();
      } else if (delBtn2) {
        if (!confirm('确定删除该评论？')) return;
        apiFetch('/api/comments/' + delBtn2.getAttribute('data-del-comment') + '/delete', { method: 'POST' })
          .then(function (d) { if (d && d.success) location.reload(); });
      } else if (foldBtn) {
        var pid = foldBtn.getAttribute('data-fold');
        var wrap = document.querySelector('.comment-children[data-parent="' + pid + '"]');
        if (wrap) {
          var hidden = wrap.style.display === 'none';
          wrap.style.display = hidden ? '' : 'none';
          foldBtn.textContent = hidden ? '收起回复' : '展开回复 (' + wrap.children.length + ')';
        }
      }
    });
    // 取消回复
    var cancelReply = el('cancelReplyBtn');
    if (cancelReply) cancelReply.addEventListener('click', function () {
      replyTarget = null;
      el('replyBar').style.display = 'none';
    });
    // 发表评论（带 parent_id）
    var submit = el('commentSubmit');
    if (submit) submit.addEventListener('click', function () {
      if (needLogin()) return;
      var content = commentContent.value.trim();
      if (!content) return;
      var body = { content: content };
      if (replyTarget) body.parent_id = replyTarget.id;
      apiFetch('/api/posts/' + postId + '/comments/create', { method: 'POST', body: body })
        .then(function (d) { if (d && d.success) location.reload(); });
    });
  }

  // ── 发帖（编辑/预览切换）──
  function initPostCreate() {
    var form = el('postCreateForm');
    if (!form) return;
    if (!app.currentUser) { location.href = '/auth'; return; }
    // 编辑器切换
    var ta = el('postContent'), preview = el('postPreview');
    document.querySelectorAll('.editor-tab').forEach(function (t) {
      t.addEventListener('click', function () {
        document.querySelectorAll('.editor-tab').forEach(function (x) { x.classList.remove('active'); });
        t.classList.add('active');
        if (t.getAttribute('data-mode') === 'preview') {
          preview.innerHTML = ta.value ? renderMarkdown(ta.value) : '<p style="color:var(--color-text-tertiary)">（空）</p>';
          preview.style.display = '';
          ta.style.display = 'none';
          enhanceContent(preview);
        } else {
          preview.style.display = 'none';
          ta.style.display = '';
        }
      });
    });
    form.addEventListener('submit', function (e) {
      e.preventDefault();
      var title = el('postTitle').value.trim();
      var content = ta.value.trim();
      var category = el('postCategory').value;
      var err = el('postError');
      if (!title || !content) { err.textContent = '标题和内容不能为空'; return; }
      apiFetch('/api/posts/create', { method: 'POST', body: { title: title, content: content, category: category } })
        .then(function (d) {
          if (!d) return;
          if (d.success) location.href = '/post/' + d.id;
          else { err.textContent = d.message || '发布失败'; }
        });
    });
  }

  // ── 搜索 ──
  function initSearch() {
    var result = el('searchResult');
    if (!result) return;
    var params = new URLSearchParams(location.search);
    var keyword = params.get('k') || '';
    var type = 'both', page = 1;
    var kwEl = el('searchKeyword');
    if (kwEl) kwEl.textContent = keyword ? '「' + keyword + '」' : '';
    function load(reset) {
      if (reset) { page = 1; result.innerHTML = '<div class="empty">加载中...</div>'; }
      apiFetch('/api/search?k=' + encodeURIComponent(keyword) + '&type=' + type + '&page=' + page + '&page_size=20')
        .then(function (d) {
          if (!d || !d.success) return;
          var html = '';
          if (type !== 'users' && d.posts) {
            html += '<div class="card-title" style="margin:8px 0;">帖子（' + d.posts_total + '）</div>';
            html += d.posts.length ? d.posts.map(postItemHtml).join('') : '<div class="empty">无相关帖子</div>';
          }
          if (type !== 'posts' && d.users) {
            html += '<div class="card-title" style="margin:8px 0;">用户（' + d.users_total + '）</div>';
            html += d.users.length ? d.users.map(function (u) {
              return '<div class="post-item">' + avatarHtml(u.avatar) +
                ' <a class="link-user" href="/users/' + esc(u.id) + '">' + esc(u.name) + '</a>' +
                (u.prefix ? '<span class="tag" style="margin-left:6px;">' + esc(u.prefix) + '</span>' : '') +
                '</div>';
            }).join('') : '<div class="empty">无相关用户</div>';
          }
          result.innerHTML = html || '<div class="empty">无结果</div>';
          resolveAvatarDeferred(result);
          var hasMore = (type !== 'users' && d.posts_has_more) || (type !== 'posts' && d.users_has_more);
          el('searchLoadMore').style.display = hasMore ? '' : 'none';
        }).catch(function () { result.innerHTML = '<div class="empty">加载失败</div>'; });
    }
    document.querySelectorAll('.search-type-tabs .tab').forEach(function (t) {
      t.addEventListener('click', function () {
        document.querySelectorAll('.search-type-tabs .tab').forEach(function (x) { x.classList.remove('active'); });
        t.classList.add('active');
        type = t.getAttribute('data-type');
        load(true);
      });
    });
    var moreBtn = el('searchLoadMoreBtn');
    if (moreBtn) moreBtn.addEventListener('click', function () { page++; load(false); });
    if (keyword) load(true);
  }

  // ── 用户页（资料 + 编辑 + 头像上传）──
  function initUserPage() {
    var profile = el('userProfile');
    if (!profile) return;
    var m = location.pathname.match(/^\/users\/([^\/]+)/);
    var userId = m ? decodeURIComponent(m[1]) : '';
    if (!userId) return;
    apiFetch('/api/user/' + encodeURIComponent(userId)).then(function (d) {
      if (!d || !d.success) { profile.innerHTML = '<div class="empty">用户不存在</div>'; return; }
      var u = d.user, s = u.stats || {};
      var isSelf = app.currentUser && app.currentUser.id === u.id;
      profile.innerHTML =
        avatarHtml(u.avatar, 'avatar-lg') +
        '<div class="user-profile-info-wrap">' +
        '<div class="user-profile-name">' + esc(u.name) + (u.prefix ? ' <span class="tag">' + esc(u.prefix) + '</span>' : '') + '</div>' +
        '<div class="user-profile-stats">' +
        '<span>帖子 ' + (s.post_count || 0) + '</span>' +
        '<button class="stat-btn" data-list="followers">粉丝 ' + (s.follower_count || 0) + '</button>' +
        '<button class="stat-btn" data-list="following">关注 ' + (s.following_count || 0) + '</button>' +
        '</div>' +
        (u.intro ? '<div class="user-profile-intro">' + esc(u.intro) + '</div>' : '') +
        '<div class="user-profile-actions">' +
        (isSelf
          ? '<button class="btn btn-sm" id="editProfileBtn"><i class="fa fa-pencil"></i> 编辑资料</button>'
          : (app.currentUser ? '<button class="btn btn-sm" id="followBtn">' + ((d.user && d.user.is_following) ? '已关注' : '关注') + '</button>' : '')) +
        '</div>' +
        '</div>';
      resolveAvatarDeferred(profile);
      var fb = el('followBtn');
      if (fb) fb.addEventListener('click', function () {
        apiFetch('/api/user/' + userId + '/follow', { method: 'POST' }).then(function (r) {
          if (r) { fb.textContent = r.following ? '已关注' : '关注'; toast(r.following ? '已关注' : '已取消关注'); }
        });
      });
      var eb = el('editProfileBtn');
      if (eb) eb.addEventListener('click', function () { openEditModal(u); });
      // 粉丝/关注数字可点击
      profile.querySelectorAll('.stat-btn').forEach(function (btn) {
        btn.addEventListener('click', function () {
          openUserListModal(userId, btn.getAttribute('data-list'), u.name);
        });
      });
      apiFetch('/api/user/' + userId + '/posts?page=1&page_size=20').then(function (pd) {
        var list = el('userPostList');
        if (pd && pd.success) {
          list.innerHTML = pd.posts.length ? pd.posts.map(postItemHtml).join('') : '<div class="empty">暂无帖子</div>';
          resolveAvatarDeferred(list);
        }
      }).catch(function () {});
      // 自己的页面加载收藏列表
      if (isSelf) {
        apiFetch('/api/user/' + userId + '/favorites?page=1&page_size=20').then(function (fd) {
          if (fd && fd.success) {
            var favCard = el('userFavCard'), favList = el('userFavList');
            if (fd.posts && fd.posts.length) {
              favList.innerHTML = fd.posts.map(postItemHtml).join('');
              resolveAvatarDeferred(favList);
              favCard.style.display = '';
            }
          }
        }).catch(function () {});
        // 自己的评论列表（点击跳转到对应帖子并定位到该评论）
        apiFetch('/api/user/' + userId + '/comments?page=1&page_size=20').then(function (cd) {
          if (cd && cd.success && cd.comments && cd.comments.length) {
            var cCard = el('userCommentCard'), cList = el('userCommentList');
            cList.innerHTML = cd.comments.map(function (c) {
              return '<div class="user-comment-item">' +
                '<div class="user-comment-text">' + esc(c.content) + '</div>' +
                '<div class="user-comment-meta">' +
                '评论于 <a class="link-user" href="/post/' + esc(c.post_id) + '#comment-' + esc(c.id) + '">' +
                esc(c.post_title || ('帖子 ' + c.post_id)) + '</a> · ' + fmtTime(c.created_at) + '</div>' +
                '</div>';
            }).join('');
            cCard.style.display = '';
          }
        }).catch(function () {});
      }
      // 个人页「我的收藏」折叠
      var userFavToggle = el('userFavToggle');
      if (userFavToggle) userFavToggle.addEventListener('click', function () {
        var body = el('userFavBody');
        if (!body) return;
        var collapsed = body.style.display === 'none';
        body.style.display = collapsed ? '' : 'none';
        userFavToggle.classList.toggle('collapsed', !collapsed);
        userFavToggle.innerHTML = collapsed ? '<i class="fa fa-angle-up"></i> 收起' : '<i class="fa fa-angle-down"></i> 展开';
      });
    }).catch(function () { profile.innerHTML = '<div class="empty">加载失败</div>'; });
  }

  // ── 粉丝/关注列表弹窗 ──
  function openUserListModal(userId, type, userName) {
    var modal = el('userListModal');
    var title = el('userListTitle');
    var body = el('userListBody');
    if (!modal) return;
    title.textContent = (type === 'followers' ? '粉丝' : '关注') + ' - ' + userName;
    body.innerHTML = '<div class="empty">加载中...</div>';
    modal.style.display = 'flex';
    apiFetch('/api/user/' + userId + '/' + type + '?page=1&page_size=50', { noAuthRedirect: true })
      .then(function (d) {
        if (!d || !d.success || !d.users || !d.users.length) {
          body.innerHTML = '<div class="empty">暂无' + (type === 'followers' ? '粉丝' : '关注') + '</div>';
          return;
        }
        body.innerHTML = d.users.map(function (u) {
          return '<div class="user-list-item">' +
            avatarHtml(u.avatar) +
            '<a class="link-user" href="/users/' + esc(u.id) + '">' + esc(u.name) + '</a>' +
            (u.prefix ? '<span class="tag" style="margin-left:6px;">' + esc(u.prefix) + '</span>' : '') +
            '</div>';
        }).join('');
        resolveAvatarDeferred(body);
      }).catch(function () { body.innerHTML = '<div class="empty">加载失败</div>'; });
  }
  function initUserListModal() {
    var modal = el('userListModal');
    if (!modal) return;
    function close() { modal.style.display = 'none'; }
    el('userListClose').addEventListener('click', close);
    modal.addEventListener('click', function (e) { if (e.target === modal) close(); });
  }

  // ── 资料编辑弹窗 ──
  // 年龄（可能存的是数字或 YYYY-MM-DD 日期）→ 统一转成 input[type=date] 需要的 yyyy-mm-dd
  function toDateValue(age) {
    if (!age) return '';
    var s = String(age).trim();
    if (/^\d{4}-\d{1,2}-\d{1,2}$/.test(s) || /^\d{4}\/\d{1,2}\/\d{1,2}$/.test(s)) {
      var parts = s.split(/[-/]/);
      return parts[0] + '-' + ('0' + parts[1]).slice(-2) + '-' + ('0' + parts[2]).slice(-2);
    }
    // 纯数字：视为年龄，空（无法映射为日期）
    if (/^\d{1,3}$/.test(s)) return '';
    return s;
  }
  function openEditModal(u) {
    var modal = el('editModal');
    if (!modal) return;
    el('editName').value = u.name || '';
    el('editGender').value = String(u.gender == null ? 0 : u.gender);
    el('editAge').value = toDateValue(u.age);
    el('editPrefix').value = u.prefix || '';
    el('editIntro').value = u.intro || '';
    el('editError').textContent = '';
    modal.style.display = 'flex';
  }

  function initEditModal() {
    var modal = el('editModal');
    if (!modal) return;
    function close() { modal.style.display = 'none'; }
    el('editClose').addEventListener('click', close);
    el('editCancel').addEventListener('click', close);
    modal.addEventListener('click', function (e) { if (e.target === modal) close(); });
    // 头像上传（先传图，成功后记 URL，保存时一并提交）
    var pendingAvatar = null;
    // 选择文件后显示文件名（美化控件）
    var avatarFileInput = el('editAvatarFile');
    if (avatarFileInput) avatarFileInput.addEventListener('change', function () {
      var nameEl = el('editAvatarFileName');
      var f = avatarFileInput.files && avatarFileInput.files[0];
      if (nameEl) nameEl.textContent = f ? f.name : '未选择文件';
    });
    el('editAvatarBtn').addEventListener('click', function () {
      var fileInput = el('editAvatarFile');
      var file = fileInput.files && fileInput.files[0];
      if (!file) { el('editError').textContent = '请先选择图片文件'; return; }
      var fd = new FormData();
      fd.append('avatar', file);
      el('editError').textContent = '上传中...';
      fetch('/api/user/avatar/upload', { method: 'POST', body: fd, credentials: 'same-origin' })
        .then(function (r) { return r.json(); })
        .then(function (d) {
          if (d && d.success) { pendingAvatar = d.avatar; el('editError').style.color = '#2ecc71'; el('editError').textContent = '头像已上传'; }
          else { el('editError').style.color = ''; el('editError').textContent = (d && d.message) || '上传失败'; }
        })
        .catch(function () { el('editError').style.color = ''; el('editError').textContent = '上传失败'; });
    });
    // 保存
    el('editSave').addEventListener('click', function () {
      var body = {
        name: el('editName').value.trim(),
        gender: parseInt(el('editGender').value, 10) || 0,
        age: el('editAge').value.trim(),
        prefix: el('editPrefix').value.trim(),
        intro: el('editIntro').value.trim()
      };
      if (pendingAvatar) body.avatar = pendingAvatar;
      apiFetch('/api/user/info', { method: 'PUT', body: body })
        .then(function (d) {
          if (!d) return;
          if (d.success) { toast('资料已更新'); location.reload(); }
          else { el('editError').style.color = ''; el('editError').textContent = d.message || '保存失败'; }
        });
    });
  }

  // ── 登录/注册/找回 ──
  var authMode = 'login';
  function switchAuthMode(mode) {
    authMode = mode;
    document.querySelectorAll('.auth-tab').forEach(function (t) {
      t.classList.toggle('active', t.getAttribute('data-mode') === mode);
    });
    el('authNameGroup').style.display = mode === 'register' ? '' : 'none';
    el('authConfirmGroup').style.display = mode === 'register' ? '' : 'none';
    var emailInput = el('authEmail');
    var emailLabel = el('authEmailLabel');
    if (mode === 'login') {
      // 登录：用户名或邮箱二选一
      if (emailLabel) emailLabel.textContent = '用户名或邮箱';
      emailInput.type = 'text';
      emailInput.placeholder = '用户名或邮箱';
      emailInput.required = true;
    } else {
      // 注册 / 找回：必须是邮箱
      if (emailLabel) emailLabel.textContent = '邮箱';
      emailInput.type = 'email';
      emailInput.placeholder = 'example@yjlt.top';
      emailInput.required = true;
    }
    el('authSubmit').textContent = mode === 'login' ? '登录' : (mode === 'register' ? '注册' : '发送重置邮件');
    el('authError').textContent = '';
  }
  window.switchAuthMode = switchAuthMode;

  function initAuthPage() {
    var form = el('authForm');
    if (!form) return;
    var m = new URLSearchParams(location.search).get('mode');
    if (m) switchAuthMode(m);
    form.addEventListener('submit', function (e) {
      e.preventDefault();
      var err = el('authError');
      var email = el('authEmail').value.trim();
      var password = el('authPassword').value;
      var name = el('authName').value.trim();
      var submit = el('authSubmit');
      // 提交期间切换为「登录中/注册中/发送中」，视觉反馈更明显
      var idleText = submit.textContent;
      var loadingText = authMode === 'login' ? '登录中…'
        : (authMode === 'register' ? '注册中…' : '发送中…');
      submit.disabled = true;
      submit.textContent = loadingText;
      var p;
      if (authMode === 'login') {
        // 用户名或邮箱二选一：含 @ 视作邮箱，否则视作用户名
        var body = { password: password };
        if (email.indexOf('@') >= 0) body.email = email;
        else body.name = email;
        p = apiFetch('/api/user/login', { method: 'POST', body: body });
      } else if (authMode === 'register') {
        if (password !== el('authConfirm').value) {
          err.textContent = '两次密码不一致';
          submit.disabled = false;
          submit.textContent = idleText;
          return;
        }
        p = apiFetch('/api/user/register', { method: 'POST', body: { name: name, email: email, password: password } });
      } else {
        p = apiFetch('/api/email/send-reset-password', { method: 'POST', body: { email: email } });
      }
      p.then(function (d) {
        if (!d) return;
        if (d.success) {
          if (authMode === 'login' || authMode === 'register') location.href = '/';
          else { err.style.color = '#2ecc71'; err.textContent = d.message || '已发送'; }
        } else {
          err.textContent = d.message || '操作失败';
        }
      }).catch(function () { err.textContent = '网络错误'; })
        .finally(function () { submit.disabled = false; submit.textContent = idleText; });
    });
  }

  // ── 右键自定义菜单（帖子/评论/页面）+ 自定义举报弹窗 ──
  function copyText(text) {
    if (!text) return;
    (navigator.clipboard ? navigator.clipboard.writeText(text) : Promise.reject())
      .then(function () { toast('已复制'); })
      .catch(function () {
        var ta = document.createElement('textarea');
        ta.value = text;
        document.body.appendChild(ta);
        ta.select();
        try { document.execCommand('copy'); toast('已复制'); } catch (e) { toast('当前浏览器不支持一键复制'); }
        document.body.removeChild(ta);
      });
  }
  function openReportModal(type, id) {
    if (!app.currentUser) { location.href = '/auth'; return; }
    var modal = el('reportModal');
    if (!modal) return;
    el('reportTargetType').value = type;
    el('reportTargetId').value = id;
    el('reportReason').value = '';
    var detail = el('reportDetail');
    if (detail) detail.value = '';
    var err = el('reportError');
    if (err) err.textContent = '';
    modal.style.display = 'flex';
  }
  function initReportModal() {
    var modal = el('reportModal');
    if (!modal) return;
    var close = el('reportClose'), cancel = el('reportCancel');
    function hide() { modal.style.display = 'none'; }
    if (close) close.addEventListener('click', hide);
    if (cancel) cancel.addEventListener('click', hide);
    modal.addEventListener('click', function (e) { if (e.target === modal) hide(); });
    var submit = el('reportSubmit');
    if (submit) submit.addEventListener('click', function () {
      var type = el('reportTargetType').value;
      var id = el('reportTargetId').value;
      var reason = el('reportReason').value.trim();
      var detail = el('reportDetail') ? el('reportDetail').value.trim() : '';
      var err = el('reportError');
      if (!reason) { if (err) err.textContent = '请选择举报原因'; return; }
      var url = type === 'post' ? '/api/posts/' + id + '/report' : '/api/comments/' + id + '/report';
      submit.disabled = true;
      apiFetch(url, { method: 'POST', body: { reason: reason, detail: detail } })
        .then(function (d) {
          if (d) { toast(d.message || '举报成功'); hide(); }
        })
        .catch(function () { if (err) err.textContent = '网络错误'; })
        .finally(function () { submit.disabled = false; });
    });
  }
  function initContextMenu() {
    var menu = el('ctxMenu');
    if (!menu) return;
    function show(items, x, y) {
      menu.innerHTML = '';
      items.forEach(function (it) {
        if (it === '-') {
          var dv = document.createElement('div');
          dv.className = 'ctx-menu-divider';
          menu.appendChild(dv);
          return;
        }
        var b = document.createElement('button');
        b.type = 'button';
        b.className = 'ctx-menu-item' + (it.danger ? ' danger' : '');
        b.innerHTML = (it.icon || '') + ' ' + esc(it.label);
        b.addEventListener('click', function (ev) {
          ev.stopPropagation();
          menu.classList.remove('open');
          it.action();
        });
        menu.appendChild(b);
      });
      // 定位防越界
      var mw = 168, mh = items.length * 42 + 14;
      menu.style.left = Math.max(4, Math.min(x, window.innerWidth - mw)) + 'px';
      menu.style.top = Math.max(4, Math.min(y, window.innerHeight - mh)) + 'px';
      menu.classList.add('open');
    }
    function hide() { menu.classList.remove('open'); }
    document.addEventListener('click', hide);
    document.addEventListener('scroll', hide, true);
    window.addEventListener('blur', hide);

    document.addEventListener('contextmenu', function (e) {
      e.preventDefault();
      var t = e.target;
      var postEl = t.closest ? t.closest('.post-item') : null;
      var commentEl = t.closest ? t.closest('.comment-item') : null;
      var isSelfPost = postEl && app.currentUser && postEl.getAttribute('data-uid') === String(app.currentUser.id);
      var isSelfComment = commentEl && app.currentUser && commentEl.getAttribute('data-cuid') === String(app.currentUser.id);
      if (commentEl) {
        var cid = commentEl.getAttribute('data-cid');
        var postLink = commentEl.getAttribute('data-post-link') || location.pathname;
        var items = [
          { label: '详情', icon: '<i class="fa fa-external-link"></i>', action: function () { location.href = postLink + '#comment-' + cid; } },
          { label: '举报', icon: '<i class="fa fa-flag-o"></i>', action: function () { openReportModal('comment', cid); } },
          { label: '分享', icon: '<i class="fa fa-share-alt"></i>', action: function () { copyText(postLink + '#comment-' + cid); } },
          { label: '复制', icon: '<i class="fa fa-copy"></i>', action: function () { var cc = commentEl.querySelector('.comment-content'); copyText(cc ? cc.textContent : ''); } }
        ];
        if (isSelfComment) {
          items.push({ label: '删除', icon: '<i class="fa fa-trash-o"></i>', danger: true, action: function () {
            apiFetch('/api/comments/' + cid + '/delete', { method: 'POST' }).then(function (d) { if (d && d.success) location.reload(); else if (d) toast(d.message || '删除失败'); });
          } });
        }
        show(items, e.clientX, e.clientY);
      } else if (postEl) {
        var pid = postEl.getAttribute('data-pid');
        var link = postEl.getAttribute('data-post-link') || '/post/' + pid;
        var items2 = [
          { label: '详情', icon: '<i class="fa fa-external-link"></i>', action: function () { location.href = link; } },
          { label: '举报', icon: '<i class="fa fa-flag-o"></i>', action: function () { openReportModal('post', pid); } },
          { label: '分享', icon: '<i class="fa fa-share-alt"></i>', action: function () { copyText(location.origin + link); } }
        ];
        if (isSelfPost) {
          items2.push({ label: '删除', icon: '<i class="fa fa-trash-o"></i>', danger: true, action: function () {
            apiFetch('/api/posts/' + pid + '/delete', { method: 'POST' }).then(function (d) { if (d && d.success) location.reload(); else if (d) toast(d.message || '删除失败'); });
          } });
        }
        show(items2, e.clientX, e.clientY);
      } else {
        show([{ label: '刷新', icon: '<i class="fa fa-refresh"></i>', action: function () { location.reload(); } }], e.clientX, e.clientY);
      }
    });
  }

  // ── 启动：先完成登录态探测，再渲染页面（避免竞态）──
  function route(path) {
    if (path === '/' || path === '') initHome();
    else if (path === '/forum') initForum();
    else if (/^\/post\/create/.test(path)) initPostCreate();
    else if (/^\/post\//.test(path)) initPostDetail();
    else if (path === '/search') initSearch();
    else if (/^\/users\//.test(path)) initUserPage();
    else if (/^\/(login|register|auth|reset-password)(\/|$)/.test(path)) initAuthPage();
    else if (path === '/Live2D') initLive2D();
    // 非 Live2D 页面启用全局浮动 Live2D
    if (path !== '/Live2D') initGlobalLive2D();
  }
  function init() {
    app.initMenus();
    app.initSearchBox();
    app.initWorldPanel();
    app.connectWorld();
    app.initWorldChat();
    initEditModal();
    initUserListModal();
    initReportModal();
    initContextMenu();
    // 解析页面已有（SSR/模板直接生成）的头像 img[data-src]，不等接口回来，立即异步触发加载。
    resolveAvatarDeferred(document);
    var path = location.pathname;
    app.initAuth().then(function () { route(path); });
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
  else init();

  // ── Live2D 独立页 ──
  function updateLive2DProgress(text, percent) {
    try {
      var fillEl = document.getElementById('live2d-progress-fill');
      var textEl = document.getElementById('live2d-progress-text');
      var percentEl = document.getElementById('live2d-progress-percent');
      if (fillEl) fillEl.style.width = percent + '%';
      if (textEl) textEl.textContent = text;
      if (percentEl) percentEl.textContent = percent + '%';
    } catch (e) {}
  }
  function hideLive2DStatus() {
    try {
      var loadingEl = document.getElementById('live2d-loading');
      var errorEl = document.getElementById('live2d-error');
      if (loadingEl) loadingEl.style.display = 'none';
      if (errorEl) errorEl.style.display = 'none';
    } catch (e) {}
  }
  function showLive2DError() {
    try {
      var loadingEl = document.getElementById('live2d-loading');
      var errorEl = document.getElementById('live2d-error');
      if (loadingEl) loadingEl.style.display = 'none';
      if (errorEl) errorEl.style.display = 'flex';
    } catch (e) {}
  }
  // ── Live2D 常量（同站主路径 + CDN 兜底回退）──
  var LPK_LOCAL   = '/static/live2d/HEI.lpk';
  var LPK_CDN     = 'https://assets.crazying-dev.top/text/one/Live2D/HEI.lpk';
  var LPKSCRIPT_LOCAL = '/static/live2d/js/Live2DLPK.js';
  var LPKSCRIPT_CDN   = 'https://assets.crazying-dev.top/text/one/JS/Live2DLPK.js';

  // 加载 Live2DLPK.js 引擎：优先同站本地，失败回退 CDN
  function _loadLpkScript(localUrl, cdnUrl) {
    return new Promise(function (resolve, reject) {
      if (typeof Live2DLPK !== 'undefined') { resolve(); return; }
      var done = false;
      function tryLoad(src, onFail) {
        var s = document.createElement('script');
        s.src = src;
        s.onload = function () { if (!done) { done = true; resolve(); } };
        s.onerror = function () {
          if (done) return;
          if (typeof onFail === 'function') onFail();
          else { done = true; reject(new Error('Live2DLPK 加载失败: ' + src)); }
        };
        document.head.appendChild(s);
      }
      tryLoad(localUrl, function () { tryLoad(cdnUrl); });
    });
  }

  // 预加载 JSZip 到全局：引擎内部固定从 cdn.jsdelivr.net 拉 JSZip，
  // 国内手机网络经常无法访问 jsdelivr（挂起无报错 → 引擎永不初始化 → 模型不显示）。
  // 只要 window.JSZip 已存在，引擎 loadScripts() 的 typeof 检查会直接跳过该依赖。
  function _ensureJSZip() {
    return new Promise(function (resolve) {
      if (typeof JSZip !== 'undefined') { resolve(); return; }
      var srcs = [
        '/static/live2d/js/jszip.min.js',                                  // 同站本地（服务器可放）
        'https://registry.npmmirror.com/jszip/3.10.1/files/dist/jszip.min.js',  // 国内镜像
        'https://cdn.staticfile.org/jszip/3.10.1/jszip.min.js',            // 国内 staticfile
        'https://unpkg.com/jszip@3.10.1/dist/jszip.min.js'                 // 兜底
      ];
      var i = 0;
      function tryNext() {
        if (i >= srcs.length) { resolve(); return; }   // 全部失败也不阻塞，交给引擎自身逻辑
        var s = document.createElement('script');
        s.src = srcs[i++];
        s.onload = function () { resolve(); };
        s.onerror = function () { tryNext(); };
        document.head.appendChild(s);
      }
      tryNext();
    });
  }

  // 加载 LPK 模型：优先同站本地，失败回退 CDN（Live2DLPK.load Promise 失败时切换 URL 重试）
  function _loadLpkModel(localUrl, cdnUrl, wrapper, opts) {
    function doLoad(url, fallback) {
      // 引擎内部用 `new PIXI.Application(...)` 渲染，默认黑色背景。
      // 在其创建 Application 之前把 PIXI.Application 包装为透明版（backgroundAlpha=0）。
      _ensurePixiTransparent();
      return Live2DLPK.load(url, wrapper, opts || {}).then(function (model) {
        _makeTransparent(model, wrapper);
        return model;
      }).catch(function (err) {
        if (fallback) {
          console.warn('[Live2D] 本地模型加载失败(' + url + ')，回退 CDN: ' + fallback);
          return doLoad(fallback, null);
        }
        throw err;
      });
    }
    return doLoad(localUrl, cdnUrl);
  }

  // 把 PIXI.Application 替换为透明版：无论引擎传什么参数，都强制 backgroundAlpha=0（透明背景）。
  var _pixiPatchStarted = false;
  function _patchPixiTransparentBackground() {
    try {
      if (typeof PIXI === 'undefined' || !PIXI.Application) return false;
      if (PIXI.Application.__patchedTransparent) return true;
      var OrigApp = PIXI.Application;
      function TransparentApp(opts) {
        opts = opts || {};
        if (!('backgroundAlpha' in opts)) opts.backgroundAlpha = 0;
        if (!('transparent' in opts)) opts.transparent = true;
        var inst = new OrigApp(opts);
        // 创建后再兜底一次：覆盖引擎显式传入的黑底配置
        try {
          var r = inst && (inst.renderer || inst);
          if (r) {
            if ('backgroundAlpha' in r) r.backgroundAlpha = 0;
            if ('transparent' in r) r.transparent = true;
          }
        } catch (e) {}
        return inst;
      }
      TransparentApp.prototype = OrigApp.prototype;
      Object.keys(OrigApp).forEach(function (k) { TransparentApp[k] = OrigApp[k]; });
      PIXI.Application = TransparentApp;
      PIXI.Application.__patchedTransparent = true;
      return true;
    } catch (e) { return false; }
  }
  // 轮询等待 PIXI 出现在全局（引擎异步加载依赖），一出现立即 patch，尽量赶在 new Application 之前。
  function _ensurePixiTransparent() {
    if (typeof PIXI !== 'undefined' && PIXI.Application) {
      _patchPixiTransparentBackground();
      return;
    }
    if (_pixiPatchStarted) return;
    _pixiPatchStarted = true;
    var tries = 0;
    var timer = setInterval(function () {
      tries++;
      if (typeof PIXI !== 'undefined' && PIXI.Application) {
        clearInterval(timer);
        _patchPixiTransparentBackground();
      } else if (tries > 300) {   // 最多轮询 15s，避免常驻定时器
        clearInterval(timer);
      }
    }, 50);
  }
  // 模型加载完成后：确保 wrapper/canvas 的 CSS 背景透明，并对返回的 model 再兜底一次。
  function _makeTransparent(model, wrapper) {
    try {
      if (wrapper) wrapper.style.background = 'transparent';
      var cv = wrapper ? wrapper.querySelector('canvas') : null;
      if (cv) cv.style.background = 'transparent';
      if (model) {
        try { model.backgroundAlpha = 0; } catch (e) {}
        try { model.transparent = true; } catch (e) {}
      }
      _patchPixiTransparentBackground();
    } catch (e) {}
  }

  function initLive2D() {
    var wrapper = document.getElementById('live2d-canvas-wrapper');
    if (!wrapper) return;
    function loadModel() {
      hideLive2DStatus();
      updateLive2DProgress('加载依赖库...', 0);
      _loadLpkScript(LPKSCRIPT_LOCAL, LPKSCRIPT_CDN).then(function () {
        _loadLpkModel(LPK_LOCAL, LPK_CDN, wrapper, { onProgress: updateLive2DProgress }).then(function () {
          var errorEl = document.getElementById('live2d-error');
          if (errorEl) errorEl.style.display = 'none';
          setTimeout(hideLive2DStatus, 300);
        }).catch(function (err) {
          console.error('Live2D load error:', err);
          showLive2DError();
        });
      }).catch(function (err) {
        console.error('Live2D bootstrap error:', err);
        showLive2DError();
      });
    }
    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', loadModel);
    else loadModel();
  }

  // ── 全局浮动 Live2D（非 /Live2D 页面） + 全屏视角跟随 ──
  var _globalLive2DLoaded = false;
  var _globalLive2DModel = null;   // 引擎加载完成后保存的 Live2DModel 实例
  var _globalLive2DFocus = { x: 0.5, y: 0.5 }; // 归一化 0-1，默认正前方
  // 全局 Live2D 共用上面定义的 _loadLpkScript / _loadLpkModel：本地优先 + CDN 回退
  // 头部跟随：优先走 pixi-live2d-display 标准的 model.focus（引擎加载后可用），
  // 同时兼容 Live2DLPK 可能暴露的 setFocus/setLookAt/updateFocus。
  function _setGlobalLive2DFocus(x, y) {
    var m = _globalLive2DModel;
    if (m && m.focus) {
      try { m.focus.x = x; m.focus.y = y; return; } catch (e) {}
    }
    try {
      if (typeof Live2DLPK !== 'undefined') {
        if (typeof Live2DLPK.setFocus === 'function') Live2DLPK.setFocus(x, y);
        else if (typeof Live2DLPK.setLookAt === 'function') Live2DLPK.setLookAt(x, y);
        else if (typeof Live2DLPK.updateFocus === 'function') Live2DLPK.updateFocus(x, y);
      }
    } catch (ee) {}
  }
  function _applyEyeTracking() {
    // 全屏范围监听 mousemove，将鼠标位置归一化为 [0,1]，作为视角方向。
    document.addEventListener('mousemove', function (e) {
      var w = window.innerWidth || document.documentElement.clientWidth || 1;
      var h = window.innerHeight || document.documentElement.clientHeight || 1;
      _globalLive2DFocus.x = Math.max(0, Math.min(1, e.clientX / w));
      _globalLive2DFocus.y = Math.max(0, Math.min(1, e.clientY / h));
      _setGlobalLive2DFocus(_globalLive2DFocus.x, _globalLive2DFocus.y);
    }, { passive: true });
    // 触屏设备：touchmove
    document.addEventListener('touchmove', function (e) {
      if (!e.touches || !e.touches[0]) return;
      var t = e.touches[0];
      var w = window.innerWidth || document.documentElement.clientWidth || 1;
      var h = window.innerHeight || document.documentElement.clientHeight || 1;
      _globalLive2DFocus.x = Math.max(0, Math.min(1, t.clientX / w));
      _globalLive2DFocus.y = Math.max(0, Math.min(1, t.clientY / h));
      _setGlobalLive2DFocus(_globalLive2DFocus.x, _globalLive2DFocus.y);
    }, { passive: true });
  }
  function initGlobalLive2D() {
    // 手机/窄屏（≤900px）不加载全局 Live2D（CSS 已隐藏，这里再跳过加载省流量）
    if (window.innerWidth <= 900) return;
    if (_globalLive2DLoaded) return;
    var wrapper = document.getElementById('global-live2d');
    if (!wrapper) return;
    _globalLive2DLoaded = true;
    // 立即启动视角跟随监听（全屏范围），即便模型还在加载
    _applyEyeTracking();
    // 点击模型：触发一个动作（引擎 autoInteract 负责 hit 区域点击，这里兜底保证“点击有反应”）
    var _clickBound = false;
    wrapper.addEventListener('click', function () {
      if (_clickBound) return;
      _clickBound = true;
      var m = _globalLive2DModel;
      if (!m) { _clickBound = false; return; }
      try {
        if (typeof m.motion === 'function') {
          m.motion('Tap', 0).catch(function () {
            try { m.motion('Idle', 0); } catch (ee2) {}
          });
        } else if (typeof Live2DLPK !== 'undefined' && typeof Live2DLPK.motion === 'function') {
          Live2DLPK.motion('Tap', 0);
        }
      } catch (ee) {}
      setTimeout(function () { _clickBound = false; }, 600);  // 防抖
    });
    _loadLpkScript(LPKSCRIPT_LOCAL, LPKSCRIPT_CDN).then(function () {
      // 传入 wrapper（含 canvas），按 wrapper 尺寸渲染；本地失败自动回退 CDN
      _loadLpkModel(LPK_LOCAL, LPK_CDN, wrapper, {}).then(function (model) {
        // 保存模型实例，供全屏鼠标跟随直接驱动 model.focus（头部跟随）
        _globalLive2DModel = model || null;
        try { if (model && model.focus) { model.focus.x = 0.5; model.focus.y = 0.5; } } catch (e) {}
      }).catch(function (err) {
        console.error('[Global Live2D] load error:', err);
        // 静默失败：不影响页面其他功能
      });
    }).catch(function (err) {
      console.error('[Global Live2D] bootstrap error:', err);
    });
  }
})();

