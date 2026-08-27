<script setup>
import { ref } from 'vue'

// 后端通过挂载点 data-port 传入第三方应用回调端口
const port = ref('')
try {
  const node = document.getElementById('app')
  port.value = node && node.dataset.port ? String(node.dataset.port) : ''
} catch (e) { port.value = '' }

const userName = ref('加载中...')
const status = ref('')
const statusOk = ref(false)
const disabled = ref(true)
let userInfo = null

async function loadUser() {
  const d = await fetch('/api/user/info', { credentials: 'same-origin' }).then((r) => r.json()).catch(() => null)
  if (d && d.success && d.user) {
    userInfo = d.user
    userName.value = userInfo.name
    disabled.value = false
  } else {
    userName.value = '未登录'
    status.value = '请先在妖精论坛登录后重试'
    statusOk.value = false
  }
}
loadUser()

function confirmAuth() {
  if (!userInfo) return
  const userData = JSON.stringify({ id: userInfo.id, name: userInfo.name, avatar: userInfo.avatar })
  window.location.href = 'http://localhost:' + port.value + '/callback?user=' + encodeURIComponent(userData)
}
</script>

<template>
  <div class="oauth-container">
    <div class="oauth-card">
      <h1>第三方授权登录</h1>
      <p>第三方应用请求访问您的论坛账号信息，请确认是否授权。</p>
      <div class="oauth-user-info"><div class="oauth-user-name">{{ userName }}</div></div>
      <div class="oauth-actions">
        <button class="oauth-btn oauth-btn-confirm" :disabled="disabled" @click="confirmAuth">授权并继续</button>
        <button class="oauth-btn oauth-btn-cancel" @click="window.close()">拒绝</button>
      </div>
      <div class="oauth-status" :class="status ? (statusOk ? 'oauth-status-ok' : 'oauth-status-err') : ''">{{ status }}</div>
    </div>
  </div>
</template>
