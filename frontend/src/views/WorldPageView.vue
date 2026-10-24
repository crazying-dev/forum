<script setup>
import { nextTick, onBeforeUnmount, onMounted, ref } from 'vue'
import { fmtTime as fmtTimeShared, getCurrentUser } from '../utils.js'

const messages = ref([])
const input = ref('')
const status = ref('连接中…')
const statusCls = ref('')
const myUserId = ref(null)
const listEl = ref(null)
const loggedIn = ref(!!getCurrentUser())

let pollTimer = null
let retry = 0

// 时间戳复用全局 AfterBody 的 fmtTime：与全站一致（含「无限年 / 公元年」年制切换）
function fmtTime(t) {
  return fmtTimeShared(t)
}

function setStatus(text, cls) {
  status.value = text
  statusCls.value = cls || ''
}

// 距底部多少像素以内算「已经贴在底部」——吸附判定的容差
const BOTTOM_SLACK = 32
function isAtBottom(el) {
  return el.scrollHeight - el.scrollTop - el.clientHeight < BOTTOM_SLACK
}

/**
 * 滚动到底部。
 *
 * 默认只在用户**本来就贴底**时跟随（聊天窗口的粘性滚动）——
 * 否则轮询刷新会把正在翻看历史消息的用户一次次拽回底部。
 * 自己发完消息时传 `force = true`，确保能立刻看到自己那条。
 *
 * 注意：是否贴底必须在 **DOM 更新前** 判断（此刻读到的仍是上一次渲染的滚动位置）。
 */
function scrollBottom(force = false) {
  const el = listEl.value
  if (!el) return
  if (!force && !isAtBottom(el)) return
  nextTick(() => { if (listEl.value) listEl.value.scrollTop = listEl.value.scrollHeight })
}

function poll(forceBottom = false) {
  if (pollTimer) { clearTimeout(pollTimer); pollTimer = null }
  if (document.hidden) { pollTimer = null; return }
  fetch('/api/world/ALL', { credentials: 'same-origin' })
    .then((r) => r.json())
    .then((data) => {
      if (Array.isArray(data)) {
        // 服务端按时间倒序返回（最新在前）；这里转成聊天顺序（最新在下），
        // 与 Windows / Android 客户端口径一致（先截最新 200 条再反转）。
        messages.value = data.slice(0, 200).reverse()
        setStatus('在线', 'online')
        retry = 0
        scrollBottom(forceBottom)
        pollTimer = setTimeout(poll, 3000)
      } else { setStatus('加载失败', 'offline'); scheduleRetry() }
    })
    .catch(() => { setStatus('连接失败', 'offline'); scheduleRetry() })
}

function scheduleRetry() {
  if (document.hidden) { pollTimer = null; return }
  const delay = Math.min(30000, 3000 * Math.pow(2, Math.min(retry, 4)))
  retry++
  pollTimer = setTimeout(poll, delay)
}

function onVisibility() {
  if (!document.hidden) { if (pollTimer) clearTimeout(pollTimer); poll() }
  else if (pollTimer) { clearTimeout(pollTimer); pollTimer = null }
}

async function send() {
  const content = input.value.trim()
  if (!content) return
  const d = await fetch('/api/world/Send', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    credentials: 'same-origin',
    body: JSON.stringify({ content }),
  }).then((r) => r.json()).catch(() => null)
  if (!d) { setStatus('发送失败', 'offline'); return }
  if (d.success) { input.value = ''; loggedIn.value = true; poll(true) }
  else if (d.message) {
    setStatus(d.message, 'offline')
    // 未登录：给出明确指引，避免只报“发送失败”却无路可走
    if (/登录/.test(d.message)) loggedIn.value = false
  } else { loggedIn.value = false }
}

function onEnter() { send() }

onMounted(() => {
  // 当前用户 id（用于标记自己的消息）
  fetch('/api/user/info', { credentials: 'same-origin' })
    .then((r) => r.json())
    .then((d) => { if (d && d.success && d.user) myUserId.value = d.user.id })
    .catch(() => {})
  document.addEventListener('visibilitychange', onVisibility)
  poll()
})

onBeforeUnmount(() => {
  if (pollTimer) clearTimeout(pollTimer)
  document.removeEventListener('visibilitychange', onVisibility)
})
</script>

<template>
  <div class="world-page-container">
    <div class="world-page-header">
      <h3><i class="fa fa-globe"></i> 世界频道</h3>
      <span class="world-page-status" :class="statusCls">{{ status }}</span>
    </div>
    <div ref="listEl" class="world-page-messages">
      <div v-if="!messages.length" class="world-page-empty">暂无消息，快来抢沙发~</div>
      <div v-for="m in messages" :key="m.id" class="world-page-msg" :class="{ mine: myUserId && m.sender_id === myUserId }">
        <span class="world-page-avatar">
          <img v-if="m.sender_avatar" :src="m.sender_avatar" alt="" loading="lazy">
          <i v-else class="fa fa-user"></i>
        </span>
        <div class="world-page-msg-body">
          <div class="world-page-msg-name">{{ m.sender_name }}</div>
          <div class="world-page-msg-content">{{ m.content }}</div>
          <div class="world-page-msg-time">{{ fmtTime(m.created_at) }}</div>
        </div>
      </div>
    </div>
    <div class="world-page-input-bar">
      <input v-model="input" type="text" placeholder="输入消息...（Enter 发送）" maxlength="500" @keydown.enter="onEnter">
      <button @click="send"><i class="fa fa-paper-plane"></i> 发送</button>
    </div>
    <div v-if="!loggedIn" class="world-page-login-tip">
      <a class="btn btn-primary btn-sm" href="/auth">登录后即可发言</a>
    </div>
  </div>
</template>
