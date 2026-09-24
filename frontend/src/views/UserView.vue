<script setup>
import { computed, nextTick, onMounted, ref } from 'vue'
import PostList from '../components/PostList.vue'
import { apiFetch, avatarHtml, esc, fmtTime, getCurrentUser, resolveAvatars, toast } from '../utils.js'

const userId = computed(() => {
  const m = location.pathname.match(/^\/users\/([^/]+)/)
  return m ? decodeURIComponent(m[1]) : ''
})
const loading = ref(true)
const notFound = ref(false)
const user = ref(null)
const posts = ref([])
const postsPage = ref(1)
const postsLoading = ref(true)
const postsLoadingMore = ref(false)
const postsHasMore = ref(true)
// 收藏/评论（仅本人）
const favPosts = ref([])
const favCollapsed = ref(false)
const favVisible = ref(false)
const myComments = ref([])
const commentsVisible = ref(false)
// 资料编辑弹窗
const editOpen = ref(false)
const editForm = ref({ name: '', gender: '0', prefix: '', intro: '' })
// 出生日期选择器（沿用 V1 组件：年 ± 步进 / 月 / 日，存库格式 YYYYMMDD）
const bpYear = ref(new Date().getFullYear())
const bpMonth = ref(1)
const bpDay = ref(1)
const bpYearEl = ref(null)
const bpDirty = ref(false)
const editError = ref('')
const editErrorColor = ref('')
const editAvatarFile = ref(null)
const pendingAvatar = ref('')
// 编辑弹窗面板：'' = 资料；'password' = 修改密码；'email' = 更换邮箱
const editPanel = ref('')
// 粉丝/关注弹窗
const listModalOpen = ref(false)
const listTitle = ref('')
const listUsers = ref([])
const listLoading = ref(false)

const me = getCurrentUser()
const isSelf = computed(() => user.value && me && me.id === user.value.id)
const followText = ref('关注')

// 生日/年龄展示（沿用 V1 __profileAgeDisplay 逻辑）：
// 空 → 保密；YYYYMMDD → 由今天算周岁 xx 岁；纯数字 → xx 岁；其它 → 保密
const ageDisplay = computed(() => {
  const s = String((user.value && user.value.age) == null ? '' : user.value.age).trim()
  if (!s) return '保密'
  if (/^\d{8}$/.test(s)) {
    const y = parseInt(s.slice(0, 4), 10)
    const m = parseInt(s.slice(4, 6), 10) - 1
    const d = parseInt(s.slice(6, 8), 10)
    const dt = new Date(y, m, d)
    if (!isNaN(dt.getTime())) {
      const now = new Date()
      let a = now.getFullYear() - dt.getFullYear()
      const md = now.getMonth() - dt.getMonth()
      if (md < 0 || (md === 0 && now.getDate() < dt.getDate())) a--
      return a + ' 岁'
    }
  }
  const n = parseInt(s, 10)
  if (!isNaN(n)) return n + ' 岁'
  return '保密'
})

// 解析已有生日：兼容 YYYYMMDD（V1 存量格式）、YYYY-MM-DD、YYYY/MM/DD
function parseAgeToYmd(age) {
  const s = String(age == null ? '' : age).trim()
  if (/^\d{8}$/.test(s)) return { y: +s.slice(0, 4), m: +s.slice(4, 6), d: +s.slice(6, 8) }
  if (/^\d{4}[-/]\d{1,2}[-/]\d{1,2}$/.test(s)) {
    const p = s.split(/[-/]/)
    return { y: +p[0], m: +p[1], d: +p[2] }
  }
  return null
}
// 选择器 → YYYYMMDD（与 V1 存库格式一致）；非法日期返回空串
function bpDateValue() {
  const y = parseInt(bpYear.value, 10)
  const m = parseInt(bpMonth.value, 10)
  const d = parseInt(bpDay.value, 10)
  if (isNaN(y) || isNaN(m) || isNaN(d)) return ''
  if (y < 100 || y > 9999 || m < 1 || m > 12 || d < 1 || d > 31) return ''
  const dt = new Date(y, m - 1, d)
  if (dt.getFullYear() !== y || dt.getMonth() !== m - 1 || dt.getDate() !== d) return ''
  return String(y).padStart(4, '0') + String(m).padStart(2, '0') + String(d).padStart(2, '0')
}
// 年份 ±1：带 V1 同款上滑/下滑过渡
function bpYearStep(delta) {
  const el = bpYearEl.value
  const cur = el ? (parseInt(el.value, 10) || 0) : (parseInt(bpYear.value, 10) || 0)
  const next = cur + delta
  bpYear.value = String(next)
  bpDirty.value = true
  if (!el) return
  const dir = delta > 0 ? -1 : 1
  el.classList.remove('bp-year-anim')
  el.style.transform = 'translateY(' + (dir * 12) + 'px)'
  el.style.opacity = '0'
  void el.offsetWidth // 强制回流，重播过渡
  el.classList.add('bp-year-anim')
  el.value = String(next)
  el.style.transform = 'translateY(' + (-dir * 12) + 'px)'
  requestAnimationFrame(() => { el.style.transform = ''; el.style.opacity = '' })
}

async function load() {
  if (!userId.value) { loading.value = false; notFound.value = true; return }
  const d = await apiFetch('/api/user/' + encodeURIComponent(userId.value))
  loading.value = false
  if (!d || !d.success) { notFound.value = true; return }
  user.value = d.user
  followText.value = (d.user && d.user.is_following) ? '已关注' : '关注'
  await nextTick()
  resolveAvatars(document)
  loadPosts(true)
  if (isSelf.value) { loadFavs(); loadComments() }
}

function loadPosts(reset) {
  if (reset) { postsPage.value = 1; posts.value = []; postsLoading.value = true }
  apiFetch('/api/user/' + userId.value + '/posts?page=' + postsPage.value + '&page_size=20').then((d) => {
    postsLoading.value = false
    postsLoadingMore.value = false
    if (!d || !d.success) return
    const arr = d.posts || []
    posts.value = reset ? arr : posts.value.concat(arr)
    postsHasMore.value = arr.length >= 20
  }).catch(() => { postsLoading.value = false; postsLoadingMore.value = false })
}
function loadMorePosts() {
  if (!postsHasMore.value || postsLoadingMore.value) return
  postsLoadingMore.value = true
  postsPage.value++
  loadPosts(false)
}
function loadFavs() {
  apiFetch('/api/user/' + userId.value + '/favorites?page=1&page_size=20').then((d) => {
    if (d && d.success && d.posts && d.posts.length) {
      favPosts.value = d.posts
      favVisible.value = true
    }
  }).catch(() => {})
}
function loadComments() {
  apiFetch('/api/user/' + userId.value + '/comments?page=1&page_size=20').then((d) => {
    if (d && d.success && d.comments && d.comments.length) {
      myComments.value = d.comments
      commentsVisible.value = true
    }
  }).catch(() => {})
}
function toggleFollow() {
  apiFetch('/api/user/' + userId.value + '/follow', { method: 'POST' }).then((r) => {
    if (r) {
      followText.value = r.following ? '已关注' : '关注'
      toast(r.following ? '已关注' : '已取消关注')
      if (user.value && user.value.stats) user.value.stats.follower_count = r.followers != null ? r.followers : user.value.stats.follower_count
    }
  })
}
// ── 粉丝/关注弹窗 ──
async function openUserList(type, name) {
  listModalOpen.value = true
  listTitle.value = (type === 'followers' ? '粉丝' : '关注') + ' - ' + name
  listUsers.value = []
  listLoading.value = true
  const d = await apiFetch('/api/user/' + userId.value + '/' + type + '?page=1&page_size=50', { noAuthRedirect: true })
    .catch(() => null)
  listLoading.value = false
  listUsers.value = (d && d.success) ? (d.users || []) : []
  await nextTick()
  resolveAvatars(document)
}
function closeList() { listModalOpen.value = false }
// ── 编辑资料弹窗 ──
function openEdit() {
  const u = user.value
  editForm.value = { name: u.name || '', gender: String(u.gender == null ? 0 : u.gender), prefix: u.prefix || '', intro: u.intro || '' }
  const ymd = parseAgeToYmd(u.age)
  bpYear.value = ymd ? String(ymd.y) : String(new Date().getFullYear())
  bpMonth.value = ymd ? ymd.m : 1
  bpDay.value = ymd ? ymd.d : 1
  bpDirty.value = false
  pendingAvatar.value = ''
  editPanel.value = ''
  // 改密码区默认清空（验证码一次性，不保留上次输入）
  pwCode.value = ''
  pwNew.value = ''
  pwConfirm.value = ''
  pwMsg.value = ''
  pwMsgColor.value = ''
  // 更换邮箱区同样清空（两步验证）
  emStep.value = 1
  emOldCode.value = ''
  emOldMsg.value = ''
  emOldMsgColor.value = ''
  emNew.value = ''
  emCode.value = ''
  emMsg.value = ''
  emMsgColor.value = ''
  editError.value = ''
  editErrorColor.value = ''
  editOpen.value = true
}
function closeEdit() { editOpen.value = false }
function onAvatarChange(e) {
  const f = e.target.files && e.target.files[0]
  editAvatarFile.value = f ? f.name : ''
}
function uploadAvatar() {
  const input = document.getElementById('editAvatarFile')
  const file = input && input.files && input.files[0]
  if (!file) { editError.value = '请先选择图片文件'; editErrorColor.value = ''; return }
  const fd = new FormData()
  fd.append('avatar', file)
  editError.value = '上传中...'
  editErrorColor.value = ''
  fetch('/api/user/avatar/upload', { method: 'POST', body: fd, credentials: 'same-origin' })
    .then((r) => r.json())
    .then((d) => {
      if (d && d.success) {
        pendingAvatar.value = d.avatar
        editError.value = '头像已上传'
        editErrorColor.value = '#2ecc71'
      } else {
        editError.value = (d && d.message) || '上传失败'
        editErrorColor.value = ''
      }
    })
    .catch(() => { editError.value = '上传失败'; editErrorColor.value = '' })
}
function saveEdit() {
  const body = {
    name: editForm.value.name.trim(),
    gender: parseInt(editForm.value.gender, 10) || 0,
    prefix: editForm.value.prefix.trim(),
    intro: editForm.value.intro.trim(),
  }
  // 生日只在用户实际改动选择器时提交，格式 YYYYMMDD（与 V1 一致）
  if (bpDirty.value) {
    const bpDate = bpDateValue()
    if (!bpDate) {
      editError.value = '出生日期不正确，请检查年 / 月 / 日'
      editErrorColor.value = ''
      return
    }
    body.age = bpDate
  }
  if (pendingAvatar.value) body.avatar = pendingAvatar.value
  apiFetch('/api/user/info', { method: 'PUT', body }).then((d) => {
    if (!d) return
    if (d.success) { toast('资料已更新'); location.reload() }
    else { editError.value = d.message || '保存失败'; editErrorColor.value = '' }
  })
}
function toggleFav() { favCollapsed.value = !favCollapsed.value }

// ── 修改密码（需邮箱验证码；用户确认口径：不要求旧密码）──
const pwCode = ref('')
const pwNew = ref('')
const pwConfirm = ref('')
const pwCooldown = ref(0)
const pwMsg = ref('')
const pwMsgColor = ref('')
let pwTimer = null
function startPwCooldown() {
  pwCooldown.value = 60
  clearInterval(pwTimer)
  pwTimer = setInterval(() => {
    pwCooldown.value -= 1
    if (pwCooldown.value <= 0) { clearInterval(pwTimer); pwTimer = null }
  }, 1000)
}
function sendPwCode() {
  if (pwCooldown.value > 0) return
  pwMsg.value = ''
  pwMsgColor.value = ''
  apiFetch('/api/email/send-change-password-code', { method: 'POST', body: {} })
    .then((d) => {
      if (!d) return
      if (d.success) {
        pwMsgColor.value = '#2ecc71'
        pwMsg.value = d.message || '验证码已发送至邮箱'
        startPwCooldown()
      } else {
        pwMsgColor.value = ''
        pwMsg.value = d.message || '发送失败'
      }
    })
    .catch(() => { pwMsg.value = '网络错误' })
}
function changePassword() {
  pwMsg.value = ''
  pwMsgColor.value = ''
  if (!pwCode.value.trim()) { pwMsg.value = '请填写邮箱验证码'; return }
  if (!pwNew.value) { pwMsg.value = '请输入新密码'; return }
  if (pwNew.value !== pwConfirm.value) { pwMsg.value = '两次新密码不一致'; return }
  apiFetch('/api/user/password', {
    method: 'POST',
    body: { code: pwCode.value.trim(), new_password: pwNew.value },
  }).then((d) => {
    if (!d) return
    if (d.success) {
      pwMsgColor.value = '#2ecc71'
      pwMsg.value = d.message || '密码修改成功'
      toast('密码修改成功，请重新登录')
      // 后端已清理登录 cookie，回到登录页重新登录
      setTimeout(() => { location.href = '/auth?mode=login' }, 1500)
    } else {
      pwMsgColor.value = ''
      pwMsg.value = d.message || '修改失败'
    }
  }).catch(() => { pwMsg.value = '网络错误' })
}

// ── 更换绑定邮箱（两步验证：先验旧邮箱身份，再验新邮箱；编辑资料中不显示当前邮箱）──
const emStep = ref(1)          // 1 = 验证当前邮箱身份；2 = 填写并验证新邮箱
const emOldCode = ref('')
const emOldCooldown = ref(0)
const emOldMsg = ref('')
const emOldMsgColor = ref('')
let emOldTimer = null
const emNew = ref('')
const emCode = ref('')
const emCooldown = ref(0)
const emMsg = ref('')
const emMsgColor = ref('')
let emTimer = null
function startEmOldCooldown() {
  emOldCooldown.value = 60
  clearInterval(emOldTimer)
  emOldTimer = setInterval(() => {
    emOldCooldown.value -= 1
    if (emOldCooldown.value <= 0) { clearInterval(emOldTimer); emOldTimer = null }
  }, 1000)
}
function startEmCooldown() {
  emCooldown.value = 60
  clearInterval(emTimer)
  emTimer = setInterval(() => {
    emCooldown.value -= 1
    if (emCooldown.value <= 0) { clearInterval(emTimer); emTimer = null }
  }, 1000)
}
function openEmailPanel() {
  editPanel.value = 'email'
  emStep.value = 1
  emOldCode.value = ''
  emOldMsg.value = ''
  emOldMsgColor.value = ''
  emNew.value = ''
  emCode.value = ''
  emMsg.value = ''
  emMsgColor.value = ''
}
// 第1步：向「当前绑定邮箱」发送验证码，验证身份
function sendOldEmailCode() {
  if (emOldCooldown.value > 0) return
  emOldMsg.value = ''
  emOldMsgColor.value = ''
  apiFetch('/api/email/send-change-email-old-code', { method: 'POST', body: {} })
    .then((d) => {
      if (!d) return
      if (d.success) {
        emOldMsgColor.value = '#2ecc71'
        emOldMsg.value = d.message || '验证码已发送至当前绑定邮箱'
        startEmOldCooldown()
      } else {
        emOldMsgColor.value = ''
        emOldMsg.value = d.message || '发送失败'
      }
    })
    .catch(() => { emOldMsg.value = '网络错误' })
}
function goEmailStep2() {
  if (!emOldCode.value.trim()) { emOldMsg.value = '请填写当前邮箱验证码'; return }
  emOldMsg.value = ''
  emStep.value = 2
}
// 第2步：向「新邮箱」发送验证码
function sendEmailCode() {
  if (emCooldown.value > 0) return
  emMsg.value = ''
  emMsgColor.value = ''
  const addr = emNew.value.trim()
  if (!addr) { emMsg.value = '请先填写新邮箱'; return }
  apiFetch('/api/email/send-change-email-code', { method: 'POST', body: { email: addr } })
    .then((d) => {
      if (!d) return
      if (d.success) {
        emMsgColor.value = '#2ecc71'
        emMsg.value = d.message || '验证码已发送至新邮箱'
        startEmCooldown()
      } else {
        emMsgColor.value = ''
        emMsg.value = d.message || '发送失败'
      }
    })
    .catch(() => { emMsg.value = '网络错误' })
}
function changeEmail() {
  emMsg.value = ''
  emMsgColor.value = ''
  const addr = emNew.value.trim()
  if (!emOldCode.value.trim()) { emStep.value = 1; emOldMsg.value = '请填写当前邮箱验证码'; return }
  if (!addr) { emMsg.value = '请先填写新邮箱'; return }
  if (!emCode.value.trim()) { emMsg.value = '请填写新邮箱验证码'; return }
  apiFetch('/api/user/email', {
    method: 'POST',
    body: { old_code: emOldCode.value.trim(), email: addr, code: emCode.value.trim() },
  }).then((d) => {
    if (!d) return
    if (d.success) {
      emMsgColor.value = '#2ecc71'
      emMsg.value = d.message || '邮箱已更换'
      toast('邮箱已更换')
      emOldCode.value = ''
      emNew.value = ''
      emCode.value = ''
      if (d.user && user.value) user.value.email = d.user.email
      setTimeout(() => { editPanel.value = ''; emStep.value = 1 }, 1200)
    } else {
      emMsgColor.value = ''
      emMsg.value = d.message || '更换失败'
    }
  }).catch(() => { emMsg.value = '网络错误' })
}

onMounted(load)
</script>

<template>
  <div class="page">
    <div v-if="loading" class="card"><div class="empty">加载中...</div></div>
    <div v-else-if="notFound" class="card"><div class="empty">用户不存在</div></div>
    <template v-else>
      <div class="card user-profile">
        <span v-html="avatarHtml(user.avatar, 'avatar-lg')"></span>
        <div class="user-profile-info-wrap">
          <div class="user-profile-name">{{ user.name }} <span v-if="user.prefix" class="tag">{{ user.prefix }}</span><span v-if="user.title" class="user-title">{{ user.title }}</span></div>
          <div class="user-profile-meta">
            <span class="user-meta-item"><i class="fa fa-birthday-cake"></i> {{ ageDisplay }}</span>
          </div>
          <div class="user-profile-stats">
            <span>帖子 {{ (user.stats && user.stats.post_count) || 0 }}</span>
            <button class="stat-btn" @click="openUserList('followers', user.name)">粉丝 {{ (user.stats && user.stats.follower_count) || 0 }}</button>
            <button class="stat-btn" @click="openUserList('following', user.name)">关注 {{ (user.stats && user.stats.following_count) || 0 }}</button>
          </div>
          <div v-if="user.intro" class="user-profile-intro">{{ user.intro }}</div>
          <div class="user-profile-actions">
            <button v-if="isSelf" class="btn btn-sm" @click="openEdit"><i class="fa fa-pencil"></i> 编辑资料</button>
            <button v-else-if="me" class="btn btn-sm" @click="toggleFollow">{{ followText }}</button>
          </div>
        </div>
      </div>

      <div v-if="favVisible" class="card">
        <div class="card-header">
          <h2 class="card-title"><i class="fa fa-bookmark-o"></i> 我的收藏</h2>
          <button class="btn btn-sm" @click="toggleFav">
            <i :class="favCollapsed ? 'fa fa-angle-down' : 'fa fa-angle-up'"></i> {{ favCollapsed ? '展开' : '收起' }}
          </button>
        </div>
        <div v-show="!favCollapsed">
          <PostList :posts="favPosts" :loading="false" empty-text="暂无收藏" />
        </div>
      </div>

      <div v-if="commentsVisible" class="card">
        <div class="card-header">
          <h2 class="card-title"><i class="fa fa-comments-o"></i> 我的评论</h2>
        </div>
        <div class="user-comment-list">
          <div v-for="c in myComments" :key="c.id" class="user-comment-item">
            <div class="user-comment-text">{{ c.content }}</div>
            <div class="user-comment-meta">
              评论于 <a class="link-user" :href="'/post/' + c.post_id + '#comment-' + c.id">{{ c.post_title || ('帖子 ' + c.post_id) }}</a> · {{ fmtTime(c.created_at) }}
            </div>
          </div>
        </div>
      </div>

      <div class="card">
        <div class="card-header">
          <h2 class="card-title"><i class="fa fa-file-text-o"></i> 发布的帖子</h2>
        </div>
        <PostList
          :posts="posts"
          :loading="postsLoading"
          :loading-more="postsLoadingMore"
          :has-more="postsHasMore"
          empty-text="暂无帖子"
          @load-more="loadMorePosts"
        />
      </div>
    </template>

    <!-- 粉丝/关注列表弹窗 -->
    <div v-if="listModalOpen" class="modal-mask" @click.self="closeList">
      <div class="modal">
        <div class="modal-header">
          <h3>{{ listTitle }}</h3>
          <button class="modal-close" @click="closeList">&times;</button>
        </div>
        <div class="user-list-modal-body">
          <div v-if="listLoading" class="empty">加载中...</div>
          <div v-else-if="!listUsers.length" class="empty">暂无成员</div>
          <div v-else>
            <div v-for="u in listUsers" :key="u.id" class="user-list-item">
              <span v-html="avatarHtml(u.avatar)"></span>
              <a class="link-user" :href="'/users/' + esc(u.id)">{{ u.name }}</a>
              <span v-if="u.prefix" class="tag" style="margin-left:6px;">{{ u.prefix }}</span>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- 编辑资料弹窗 -->
    <div v-if="editOpen" class="modal-mask" @click.self="closeEdit">
      <div class="modal">
        <div class="modal-header">
          <h3><i class="fa fa-user"></i> {{ editPanel === 'password' ? '修改密码' : editPanel === 'email' ? '更换绑定邮箱' : '编辑资料' }}</h3>
          <button class="modal-close" @click="closeEdit">&times;</button>
        </div>
        <!-- 面板：修改密码（不显示邮箱） -->
        <template v-if="editPanel === 'password'">
          <div class="form-hint">系统会向你的绑定邮箱发送 6 位验证码，验证后即可设置新密码（无需旧密码）。</div>
          <div class="form-group">
            <label>邮箱验证码</label>
            <div class="code-row">
              <input v-model="pwCode" type="text" maxlength="6" placeholder="6 位数字验证码">
              <button type="button" class="btn btn-outline btn-sm" :disabled="pwCooldown > 0" @click="sendPwCode">
                {{ pwCooldown > 0 ? pwCooldown + 's' : '获取验证码' }}
              </button>
            </div>
          </div>
          <div class="form-group">
            <label>新密码</label>
            <input v-model="pwNew" type="password" maxlength="64" placeholder="至少 8 位，含字母和数字">
          </div>
          <div class="form-group">
            <label>确认新密码</label>
            <input v-model="pwConfirm" type="password" maxlength="64">
          </div>
          <p class="auth-error" :style="pwMsgColor ? { color: pwMsgColor } : {}">{{ pwMsg }}</p>
          <div class="modal-actions">
            <button class="btn btn-outline" @click="editPanel = ''">返回</button>
            <button class="btn btn-primary" @click="changePassword"><i class="fa fa-key"></i> 修改密码</button>
          </div>
        </template>

        <!-- 面板：更换邮箱（两步：旧邮箱身份 → 新邮箱） -->
        <template v-else-if="editPanel === 'email'">
          <p class="form-hint">{{ emStep === 1 ? '第 1 步 / 共 2 步：验证当前绑定邮箱身份' : '第 2 步 / 共 2 步：填写并验证新邮箱' }}</p>
          <template v-if="emStep === 1">
            <div class="form-group">
              <label>当前邮箱验证码</label>
              <div class="code-row">
                <input v-model="emOldCode" type="text" maxlength="6" placeholder="6 位数字验证码">
                <button type="button" class="btn btn-outline btn-sm" :disabled="emOldCooldown > 0" @click="sendOldEmailCode">
                  {{ emOldCooldown > 0 ? emOldCooldown + 's' : '获取验证码' }}
                </button>
              </div>
            </div>
            <p class="auth-error" :style="emOldMsgColor ? { color: emOldMsgColor } : {}">{{ emOldMsg }}</p>
            <div class="modal-actions">
              <button class="btn btn-outline" @click="editPanel = ''">返回</button>
              <button class="btn btn-primary" @click="goEmailStep2">下一步</button>
            </div>
          </template>
          <template v-else>
            <div class="form-group">
              <label>新邮箱</label>
              <input v-model="emNew" type="email" maxlength="120" placeholder="新邮箱地址">
            </div>
            <div class="form-group">
              <label>新邮箱验证码</label>
              <div class="code-row">
                <input v-model="emCode" type="text" maxlength="6" placeholder="6 位数字验证码">
                <button type="button" class="btn btn-outline btn-sm" :disabled="emCooldown > 0" @click="sendEmailCode">
                  {{ emCooldown > 0 ? emCooldown + 's' : '获取验证码' }}
                </button>
              </div>
            </div>
            <p class="auth-error" :style="emMsgColor ? { color: emMsgColor } : {}">{{ emMsg }}</p>
            <div class="modal-actions">
              <button class="btn btn-outline" @click="emStep = 1">上一步</button>
              <button class="btn btn-primary" @click="changeEmail"><i class="fa fa-envelope-o"></i> 确认更换</button>
            </div>
          </template>
        </template>

        <!-- 面板：编辑资料 -->
        <template v-else>
        <div class="form-group">
          <label>昵称</label>
          <input v-model="editForm.name" type="text" maxlength="20">
        </div>
        <div class="form-group">
          <label>性别</label>
          <select v-model="editForm.gender">
            <option value="0">未设置</option>
            <option value="1">男</option>
            <option value="2">女</option>
          </select>
        </div>
        <div class="form-group">
          <label>出生日期</label>
          <div class="birthday-picker">
            <button type="button" class="bp-arrow" title="上一年" @click="bpYearStep(-1)"><i class="fa fa-chevron-left"></i></button>
            <div class="bp-year-wrap">
              <input ref="bpYearEl" v-model="bpYear" class="bp-year" type="number" @input="bpDirty = true">
            </div>
            <button type="button" class="bp-arrow" title="下一年" @click="bpYearStep(1)"><i class="fa fa-chevron-right"></i></button>
            <span class="bp-sep">-</span>
            <input v-model="bpMonth" class="bp-month" type="number" min="1" max="12" @input="bpDirty = true">
            <span class="bp-sep">-</span>
            <input v-model="bpDay" class="bp-day" type="number" min="1" max="31" @input="bpDirty = true">
          </div>
        </div>
        <div class="form-group">
          <label>称号前缀</label>
          <input v-model="editForm.prefix" type="text" maxlength="32" placeholder="如：妖精">
        </div>
        <div class="form-group">
          <label>简介</label>
          <textarea v-model="editForm.intro" rows="3" maxlength="200"></textarea>
        </div>
        <div class="form-group">
          <label>头像</label>
          <div class="avatar-upload">
            <input type="file" id="editAvatarFile" accept="image/*" @change="onAvatarChange">
            <label class="avatar-pick" for="editAvatarFile"><i class="fa fa-image"></i> 选择图片</label>
            <span class="avatar-file-name">{{ editAvatarFile || '未选择文件' }}</span>
            <button type="button" class="btn btn-sm btn-outline" @click="uploadAvatar">上传头像</button>
          </div>
          <p class="auth-error" :style="editErrorColor ? { color: editErrorColor } : {}">{{ editError }}</p>
        </div>
        <div class="setting-divider"></div>
        <div class="form-hint">账号安全：修改密码 / 更换绑定邮箱均需邮箱验证码。</div>
        <div class="modal-actions" style="justify-content:flex-start; gap:8px; flex-wrap:wrap; margin-bottom:4px;">
          <button type="button" class="btn btn-outline" @click="editPanel = 'password'"><i class="fa fa-key"></i> 修改密码</button>
          <button type="button" class="btn btn-outline" @click="openEmailPanel"><i class="fa fa-envelope-o"></i> 修改邮箱</button>
        </div>
        <div class="modal-actions">
          <button class="btn btn-outline" @click="closeEdit">取消</button>
          <button class="btn btn-primary" @click="saveEdit">保存</button>
        </div>
        </template>
      </div>
    </div>
  </div>
</template>
