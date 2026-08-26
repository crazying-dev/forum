// Vue3 共享工具层：复用 AfterBody.js 的 __yoyoApp（API 去重缓存 / 时区时间 / 头像延迟加载 / 举报弹窗）
const app = window.__yoyoApp || {}

export function apiFetch(url, opts) {
  return app.apiFetch ? app.apiFetch(url, opts) : fetch(url, opts).then((r) => r.json())
}
export function esc(s) {
  return app.esc ? app.esc(s) : String(s ?? '')
}
export function fmtTime(t) {
  return app.fmtTime ? app.fmtTime(t) : (t || '')
}
export function toast(msg) {
  return app.toast ? app.toast(msg) : null
}
export function avatarHtml(url, cls) {
  // 头像延迟加载：真实 URL 进 data-src，渲染后再 resolveAvatars() 注入 src
  return app.avatarHtml ? app.avatarHtml(url, cls) : ''
}
export function resolveAvatars(scope) {
  return app.resolveAvatarDeferred ? app.resolveAvatarDeferred(scope) : null
}
export function getCurrentUser() {
  return app.currentUser || null
}
export function initAuth() {
  return app.initAuth ? app.initAuth() : Promise.resolve(null)
}
// 未登录守卫：跳转 /auth
export function needLogin() {
  if (!getCurrentUser()) {
    location.href = '/auth'
    return false
  }
  return true
}
// 打开举报弹窗（AfterBody 暴露的全局方法）
export function openReportModal(type, id) {
  if (app.openReportModal) return app.openReportModal(type, id)
}

// ── 帖子分类汉化（与 AfterBody.js CATEGORY_MAP 保持一致） ──
export const CATEGORY_MAP = {
  general: '综合',
  叶羽: '叶羽',
  创意: '创意',
  求助: '求助',
  // V1 存量分类兼容
  talk: '闲聊',
  question: '求助',
  share: '分享',
  creative: '创作',
}
export function categoryLabel(c) {
  const key = c || 'general'
  return CATEGORY_MAP[key] || key
}

// ── Markdown 渲染（复用 base.html 全局 marked，与 AfterBody renderMarkdown 一致） ──
// 渲染结果经外链清洗（_sanitizeHtml）：危险标签/事件属性移除，外部链接改写为 /GoTo 安全确认页
export function sanitizeHtml(html) {
  return app.sanitizeHtml ? app.sanitizeHtml(html) : html
}
export function isExternalLink(href) {
  return app.isExternalLink ? app.isExternalLink(href) : false
}
export function rewriteLinks(container) {
  if (app.rewriteLinks) return app.rewriteLinks(container)
  if (!container) return
  container.querySelectorAll('a[href]').forEach((a) => {
    const href = a.getAttribute('href')
    if (isExternalLink(href)) a.setAttribute('href', '/GoTo?to=' + encodeURIComponent(href))
    a.setAttribute('rel', 'nofollow noopener noreferrer')
    a.setAttribute('target', '_blank')
  })
}
export function renderMarkdown(text) {
  if (!text) return ''
  if (typeof marked !== 'undefined' && marked.parse) {
    try {
      return sanitizeHtml(marked.parse(text))
    } catch (e) { /* 失败走兜底 */ }
  }
  return '<p>' + esc(text) + '</p>'
}

// 内容后处理：图片懒加载 + 代码块复制按钮 + 外链改写（与 AfterBody enhanceContent 一致）
export function enhanceContent(container) {
  if (!container) return
  rewriteLinks(container)
  container.querySelectorAll('img').forEach(function (img) {
    if (!img.getAttribute('loading')) img.setAttribute('loading', 'lazy')
  })
  container.querySelectorAll('pre code, pre').forEach(function (pre) {
    if (pre.closest('.code-copy-wrap')) return
    var wrap = document.createElement('div')
    wrap.className = 'code-copy-wrap'
    var btn = document.createElement('button')
    btn.className = 'code-copy-btn'
    btn.textContent = '复制'
    btn.addEventListener('click', function () {
      var text = pre.innerText || pre.textContent || ''
      ;(navigator.clipboard ? navigator.clipboard.writeText(text) : Promise.reject())
        .then(function () { toast('已复制') })
        .catch(function () {
          var ta = document.createElement('textarea')
          ta.value = text
          document.body.appendChild(ta)
          ta.select()
          try { document.execCommand('copy'); toast('已复制') } catch (e) { toast('复制失败') }
          document.body.removeChild(ta)
        })
    })
    pre.parentNode.insertBefore(wrap, pre)
    wrap.appendChild(pre)
    wrap.appendChild(btn)
  })
}
