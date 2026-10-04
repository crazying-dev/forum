<script setup>
// 滑块拼图人机验证：弹出式弹窗，capture() 返回 Promise<{ token }>
// 打开时请求 /api/captcha/challenge，拖动拼图块后调 /api/captcha/verify，
// 通过后把 token 交给调用方，由调用方塞进真实业务请求体的 captcha_token 字段。
import { ref } from 'vue'
import { apiFetch } from '../utils.js'

const visible = ref(false)
const loading = ref(false)
const submitting = ref(false)
const errMsg = ref('')
const bg = ref('')
const piece = ref('')
const meta = ref({ y: 0, width: 320, height: 180, pieceSize: 50 })
const dragX = ref(0)

let token = ''
let resolver = null
let rejecter = null
let dragging = false
let startPointerX = 0
let startDragX = 0

function _maxDrag() {
  return Math.max(0, meta.value.width - meta.value.pieceSize)
}

async function fetchChallenge() {
  loading.value = true
  errMsg.value = ''
  dragX.value = 0
  try {
    const d = await apiFetch('/api/captcha/challenge', { method: 'POST', body: {} })
    if (!d || !d.success) throw new Error((d && d.message) || '加载失败')
    // 服务端已关闭人机验证：直接放行（captcha_token 留空）
    if (d.enabled === false) { _resolve({ token: '' }); return }
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
    fetchChallenge()
  })
}

function _resolve(val) {
  visible.value = false
  const r = resolver
  resolver = null
  rejecter = null
  if (r) r(val)
}

function cancel() {
  visible.value = false
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
      <p class="captcha-err">{{ errMsg }}</p>
      <div class="captcha-actions">
        <button type="button" class="btn btn-outline btn-sm" @click="fetchChallenge">刷新</button>
        <button type="button" class="btn btn-outline btn-sm" @click="cancel">取消</button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.captcha-mask {
  position: fixed;
  inset: 0;
  z-index: 9999;
  background: rgba(0, 0, 0, 0.55);
  display: flex;
  align-items: center;
  justify-content: center;
}
.captcha-box {
  background: var(--card-bg, #fff);
  color: var(--text, #222);
  border-radius: 12px;
  padding: 16px;
  box-shadow: 0 10px 40px rgba(0, 0, 0, 0.3);
  max-width: 96vw;
}
.captcha-title { font-size: 16px; font-weight: 700; margin-bottom: 4px; }
.captcha-tip { font-size: 13px; opacity: 0.75; margin-bottom: 10px; }
.captcha-stage {
  position: relative;
  overflow: hidden;
  border-radius: 8px;
  user-select: none;
  touch-action: none;
}
.captcha-bg { display: block; }
.captcha-piece { position: absolute; left: 0; pointer-events: none; }
.captcha-loading {
  position: absolute; inset: 0;
  display: flex; align-items: center; justify-content: center;
  font-size: 14px; color: #fff; background: rgba(0, 0, 0, 0.35);
}
.captcha-track {
  position: relative;
  height: 40px;
  margin-top: 12px;
  border-radius: 20px;
  background: #eee;
  border: 1px solid #ddd;
  user-select: none;
  touch-action: none;
}
.captcha-fill { position: absolute; top: 0; left: 0; bottom: 0; background: rgba(106, 140, 137, 0.25); border-radius: 20px; }
.captcha-handle {
  position: absolute; top: 0; left: 0;
  width: 40px; height: 40px; line-height: 40px; text-align: center;
  border-radius: 20px;
  background: #6a8c89; color: #fff; font-weight: 700;
  cursor: grab; touch-action: none;
}
.captcha-err { min-height: 18px; margin: 8px 0 0; font-size: 13px; color: #e74c3c; }
.captcha-actions { display: flex; gap: 8px; justify-content: flex-end; margin-top: 6px; }
</style>
