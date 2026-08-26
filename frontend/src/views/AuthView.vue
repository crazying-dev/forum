<script setup>
import { computed, ref } from 'vue'
import { apiFetch } from '../utils.js'

// 初始模式：URL ?mode= 优先，其次模板 data-mode（Flask 渲染）
const mountEl = document.getElementById('app')
const rawMode = (new URLSearchParams(location.search).get('mode')) || (mountEl && mountEl.dataset.mode) || 'login'
const mode = ref(['login', 'register', 'reset'].includes(rawMode) ? rawMode : 'login')
// 找回密码：邮件链接带 ?token= → 直接进入"设置新密码"步骤
const token = (new URLSearchParams(location.search).get('token')) || ''
const name = ref('')
const email = ref('')
const code = ref('')
const password = ref('')
const confirm = ref('')
const error = ref('')
const errorColor = ref('')
const submitting = ref(false)
const codeCooldown = ref(0)
let codeTimer = null

// 重置密码且携带 token：进入设置新密码表单（不再显示邮箱输入）
const isResetWithToken = computed(() => mode.value === 'reset' && !!token)
const showName = computed(() => mode.value === 'register')
const showEmail = computed(() => !isResetWithToken.value)
const showConfirm = computed(() => mode.value === 'register' || isResetWithToken.value)
const showCode = computed(() => mode.value === 'register')
const emailLabel = computed(() => (mode.value === 'register' ? '邮箱' : '用户名或邮箱'))
const emailPlaceholder = computed(() => (mode.value === 'register' ? '邮箱' : '用户名或邮箱'))

function switchMode(m) {
  mode.value = m
  error.value = ''
  errorColor.value = ''
}

function startCodeCooldown() {
  codeCooldown.value = 60
  clearInterval(codeTimer)
  codeTimer = setInterval(() => {
    codeCooldown.value -= 1
    if (codeCooldown.value <= 0) { clearInterval(codeTimer); codeTimer = null }
  }, 1000)
}

function sendCode() {
  if (codeCooldown.value > 0) return
  error.value = ''
  errorColor.value = ''
  const em = email.value.trim()
  if (!em) { error.value = '请先输入邮箱'; return }
  apiFetch('/api/email/send-register-code', { method: 'POST', body: { email: em } })
    .then((d) => {
      if (!d) return
      if (d.success) { errorColor.value = '#2ecc71'; error.value = d.message || '验证码已发送'; startCodeCooldown() }
      else { errorColor.value = ''; error.value = d.message || '发送失败' }
    })
    .catch(() => { error.value = '网络错误' })
}

function submit() {
  error.value = ''
  errorColor.value = ''
  if (submitting.value) return
  const m = mode.value
  if ((m === 'register' || isResetWithToken.value) && password.value !== confirm.value) {
    error.value = '两次密码不一致'
    return
  }
  submitting.value = true
  let p
  if (m === 'login') {
    // 用户名或邮箱二选一：含 @ 视作邮箱，否则视作用户名
    const body = { password: password.value }
    if (email.value.indexOf('@') >= 0) body.email = email.value
    else body.name = email.value
    p = apiFetch('/api/user/login', { method: 'POST', body })
  } else if (m === 'register') {
    p = apiFetch('/api/user/register', {
      method: 'POST',
      body: { name: name.value, email: email.value, password: password.value, code: code.value.trim() },
    })
  } else if (isResetWithToken.value) {
    // 设置新密码：POST token + 新密码
    p = apiFetch('/api/email/reset-password', {
      method: 'POST',
      body: { token, password: password.value },
    })
  } else {
    p = apiFetch('/api/email/send-reset-password', { method: 'POST', body: { email: email.value } })
  }
  p.then((d) => {
    if (!d) return
    if (d.success) {
      if (m === 'login' || m === 'register') location.href = '/'
      else {
        errorColor.value = '#2ecc71'
        error.value = d.message || '已发送'
        // 设置新密码成功后跳回登录
        if (isResetWithToken.value) {
          setTimeout(() => { location.href = '/auth?mode=login' }, 1500)
        }
      }
    } else {
      error.value = d.message || '操作失败'
    }
  }).catch(() => { error.value = '网络错误' })
    .finally(() => { submitting.value = false })
}
</script>

<template>
  <div class="page page-center">
    <div class="card auth-card">
      <div class="auth-tabs">
        <button class="auth-tab" :class="{ active: mode === 'login' }" @click="switchMode('login')">登录</button>
        <button class="auth-tab" :class="{ active: mode === 'register' }" @click="switchMode('register')">注册</button>
        <button class="auth-tab" :class="{ active: mode === 'reset' }" @click="switchMode('reset')">找回密码</button>
      </div>
      <form @submit.prevent="submit" autocomplete="off">
        <div v-show="showName" class="form-group">
          <label>用户名</label>
          <input v-model="name" type="text" maxlength="20" placeholder="2-20 个字符">
        </div>
        <div v-show="showEmail" class="form-group">
          <label>{{ emailLabel }}</label>
          <input v-model="email" type="text" maxlength="255" :placeholder="emailPlaceholder">
        </div>
        <div v-show="showCode" class="form-group form-group-inline">
          <label>邮箱验证码</label>
          <div class="code-row">
            <input v-model="code" type="text" maxlength="6" placeholder="6 位数字验证码">
            <button type="button" class="btn btn-outline btn-sm" :disabled="codeCooldown > 0" @click="sendCode">
              {{ codeCooldown > 0 ? codeCooldown + 's' : '获取验证码' }}
            </button>
          </div>
        </div>
        <div class="form-group">
          <label>{{ isResetWithToken ? '新密码' : '密码' }}</label>
          <input v-model="password" type="password" maxlength="64" placeholder="至少 8 位，含字母和数字">
        </div>
        <div v-show="showConfirm" class="form-group">
          <label>确认密码</label>
          <input v-model="confirm" type="password" maxlength="64">
        </div>
        <p class="auth-error" :style="errorColor ? { color: errorColor } : {}">{{ error }}</p>
        <button type="submit" class="btn btn-primary btn-block" :disabled="submitting">
          {{ submitting ? (mode === 'login' ? '登录中…' : (mode === 'register' ? '注册中…' : (isResetWithToken ? '提交中…' : '发送中…'))) : (mode === 'login' ? '登录' : (mode === 'register' ? '注册' : (isResetWithToken ? '设置新密码' : '发送重置邮件'))) }}
        </button>
      </form>
    </div>
  </div>
</template>
