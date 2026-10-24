<script setup>
// 人机验证弹窗：统一外壳，按服务端 /api/captcha/challenge 返回的 provider 分流。
//   provider=slider    → 自研滑块拼图（拖动拼图块 → /api/captcha/verify）
//   provider=turnstile → Cloudflare Turnstile 官方组件（回调直接给 token）
//   enabled=false      → 服务端已关闭，直接放行
// capture() 返回 Promise<{ token }>，token 由调用方塞进业务请求体的 captcha_token 字段。
//
// 注意：样式全部放在全局 main.css —— Vite 以 JS 为入口构建，SFC 内的 <style>
// 只会被抽成独立 CSS 资源却没有 HTML 去 <link>，曾导致弹窗样式整体丢失。
import { ref, nextTick } from 'vue'
import { apiFetch } from '../utils.js'

const TURNSTILE_SRC =
  'https://challenges.cloudflare.com/turnstile/v0/api.js?render=explicit'

const visible = ref(false)
const provider = ref('slider')
const loading = ref(false)
const submitting = ref(false)
const errMsg = ref('')
const bg = ref('')
const piece = ref('')
const meta = ref({ y: 0, width: 320, height: 180, pieceSize: 50 })
const dragX = ref(0)
const sitekey = ref('')
const tsHost = ref(null)
// Turnstile 解不出来时的回退：一旦置位，后续挑战一律强制 ?provider=slider
const sliderOnly = ref(false)
let triedFallback = false

let token = ''
let resolver = null
let rejecter = null
let dragging = false
let startPointerX = 0
let startDragX = 0
let widgetId = null
let tsScriptLoading = null

function _theme() {
  return document.documentElement.classList.contains('night-mode') ? 'dark' : 'light'
}

function _loadTurnstileScript() {
  if (window.turnstile) return Promise.resolve()
  if (tsScriptLoading) return tsScriptLoading
  tsScriptLoading = new Promise((resolve, reject) => {
    window.__tsOnload = function () { resolve() }
    const s = document.createElement('script')
    s.src = TURNSTILE_SRC + '&onload=__tsOnload'
    s.async = true
    s.onerror = function () { tsScriptLoading = null; reject(new Error('验证服务加载失败，请检查网络')) }
    document.head.appendChild(s)
  })
  return tsScriptLoading
}

async function _renderTurnstile() {
  try {
    await _loadTurnstileScript()
  } catch (e) {
    errMsg.value = (e && e.message) || '验证服务加载失败'
    _fallbackToSlider()
    return
  }
  const host = tsHost.value
  if (!host || !window.turnstile) {
    errMsg.value = '验证服务不可用，请重试'
    _fallbackToSlider()
    return
  }
  _cleanupWidget()
  host.innerHTML = ''
  try {
    widgetId = window.turnstile.render(host, {
      sitekey: sitekey.value,
      theme: _theme(),
      language: 'zh-cn',
      callback: function (tok) { if (tok) _resolve({ token: tok }) },
      'error-callback': function () {
        errMsg.value = '人机验证失败，请重试'
        _fallbackToSlider()
        return true
      },
      'timeout-callback': function () {
        errMsg.value = '验证超时，请重试'
        _fallbackToSlider()
        return true
      },
      'expired-callback': function () { errMsg.value = '验证已过期，请重新验证' },
    })
  } catch (e) {
    errMsg.value = '组件初始化失败，请刷新重试'
    _fallbackToSlider()
  }
}

// Turnstile 出错 / 加载失败 / 超时 → 自动改用自研滑块（只回退一次，避免来回抖动）。
// 服务端 ?provider=slider 会强制下发拼图挑战，即使全局 provider 仍是 turnstile。
function _fallbackToSlider() {
  if (triedFallback) return false
  triedFallback = true
  sliderOnly.value = true
  _cleanupWidget()
  fetchChallenge()
  return true
}

function _cleanupWidget() {
  try {
    if (widgetId !== null && window.turnstile) window.turnstile.remove(widgetId)
  } catch (e) { /* ignore */ }
  widgetId = null
}

function _maxDrag() {
  return Math.max(0, meta.value.width - meta.value.pieceSize)
}

async function fetchChallenge() {
  loading.value = true
  errMsg.value = ''
  dragX.value = 0
  try {
    const url = sliderOnly.value
      ? '/api/captcha/challenge?provider=slider'
      : '/api/captcha/challenge'
    const d = await apiFetch(url, { method: 'POST', body: {} })
    if (!d || !d.success) throw new Error((d && d.message) || '加载失败')
    // 服务端已关闭人机验证：直接放行（captcha_token 留空）
    if (d.enabled === false) { _resolve({ token: '' }); return }
    provider.value = d.provider || 'slider'
    if (provider.value === 'turnstile') {
      sitekey.value = d.sitekey || ''
      if (!sitekey.value) {
        // 服务端没给 sitekey（理论上不会发生）→ 改走自研滑块，不能白屏
        if (!_fallbackToSlider()) throw new Error('验证服务未配置')
        return
      }
      await nextTick()
      loading.value = false
      await _renderTurnstile()
      return
    }
    token = d.token
    bg.value = d.bg || ''
    piece.value = d.piece || ''
    meta.value = {
      y: d.y || 0,
      width: d.width || 320,
      height: d.height || 180,
      pieceSize: d.piece_size || 50,
    }
  } catch (e) {
    errMsg.value = (e && e.message) || '加载失败，请刷新重试'
  } finally {
    loading.value = false
  }
}

// 对外接口：打开弹窗并等待用户完成验证
function capture() {
  return new Promise((resolve, reject) => {
    resolver = resolve
    rejecter = reject
    visible.value = true
    // 等弹窗 DOM（含 Turnstile 挂载点）渲染完成后再取挑战
    nextTick().then(fetchChallenge)
  })
}

// 重试：Turnstile走官方 reset，滑块重新取挑战
async function retry() {
  errMsg.value = ''
  if (provider.value === 'turnstile') {
    if (widgetId !== null && window.turnstile) {
      try { window.turnstile.reset(widgetId); return } catch (e) { /* fallthrough */ }
    }
    await _renderTurnstile()
    return
  }
  await fetchChallenge()
}

function _resolve(val) {
  visible.value = false
  _cleanupWidget()
  const r = resolver
  resolver = null
  rejecter = null
  if (r) r(val)
}

function cancel() {
  visible.value = false
  _cleanupWidget()
  const rj = rejecter
  resolver = null
  rejecter = null
  if (rj) rj(new Error('captcha-cancelled'))
}

function onPointerDown(e) {
  if (loading.value) return
  dragging = true
  startPointerX = e.clientX
  startDragX = dragX.value
  window.addEventListener('pointermove', onPointerMove)
  window.addEventListener('pointerup', onPointerUp)
}
function onPointerMove(e) {
  if (!dragging) return
  const next = startDragX + (e.clientX - startPointerX)
  dragX.value = Math.max(0, Math.min(_maxDrag(), next))
}
function onPointerUp() {
  if (!dragging) return
  dragging = false
  window.removeEventListener('pointermove', onPointerMove)
  window.removeEventListener('pointerup', onPointerUp)
  submit()
}

async function submit() {
  if (submitting.value || loading.value) return
  if (!token) { await fetchChallenge(); return }
  submitting.value = true
  errMsg.value = ''
  try {
    const d = await apiFetch('/api/captcha/verify', {
      method: 'POST',
      body: { captcha_token: token, captcha_x: dragX.value },
    })
    if (d && d.success) { _resolve({ token: d.token || token }); return }
    errMsg.value = (d && d.message) || '验证失败，请重试'
    await fetchChallenge()
  } catch (e) {
    errMsg.value = '网络错误，请重试'
  } finally {
    submitting.value = false
  }
}

defineExpose({ capture })
</script>

<template>
  <div v-if="visible" class="captcha-mask" @click.self="cancel">
    <div class="captcha-box" role="dialog" aria-label="安全验证">
      <div class="captcha-title">安全验证</div>

      <!-- Turnstile：官方托管组件，回调即拿到 token -->
      <template v-if="provider === 'turnstile'">
        <div class="captcha-tip">请完成下方验证</div>
        <div ref="tsHost" class="captcha-ts"></div>
      </template>

      <!-- 自研滑块拼图 -->
      <template v-else>
        <div class="captcha-tip">拖动下方滑块，把拼图块放入缺口</div>
        <div class="captcha-stage" :style="{ width: meta.width + 'px', height: meta.height + 'px' }">
          <img v-if="bg" class="captcha-bg" :src="bg" :width="meta.width" :height="meta.height" alt="">
          <img
            v-if="piece"
            class="captcha-piece"
            :src="piece"
            :style="{ left: dragX + 'px', top: meta.y + 'px', width: meta.pieceSize + 'px', height: meta.pieceSize + 'px' }"
            alt=""
          >
          <div v-if="loading" class="captcha-loading">加载中…</div>
        </div>
        <div class="captcha-track" :style="{ width: meta.width + 'px' }">
          <div class="captcha-fill" :style="{ width: (dragX + meta.pieceSize / 2) + 'px' }"></div>
          <div
            class="captcha-handle"
            :style="{ left: dragX + 'px' }"
            @pointerdown.prevent="onPointerDown"
          >»</div>
        </div>
      </template>

      <p class="captcha-err">{{ errMsg }}</p>
      <div class="captcha-actions">
        <button type="button" class="btn btn-outline btn-sm" @click="retry">刷新</button>
        <button type="button" class="btn btn-outline btn-sm" @click="cancel">取消</button>
      </div>
    </div>
  </div>
</template>


