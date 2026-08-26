<script setup>
import { computed, onMounted, ref } from 'vue'
import PostList from '../components/PostList.vue'
import { apiFetch, avatarHtml, esc, fmtTime, getCurrentUser, toast } from '../utils.js'

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
const editForm = ref({ name: '', gender: '0', age: '', prefix: '', intro: '' })
const editError = ref('')
const editErrorColor = ref('')
const editAvatarFile = ref(null)
const pendingAvatar = ref('')
// 粉丝/关注弹窗
const listModalOpen = ref(false)
const listTitle = ref('')
const listUsers = ref([])
const listLoading = ref(false)

const me = getCurrentUser()
const isSelf = computed(() => user.value && me && me.id === user.value.id)
const followText = ref('关注')

function toDateValue(age) {
  if (!age) return ''
  const s = String(age).trim()
  if (/^\d{4}-\d{1,2}-\d{1,2}$/.test(s) || /^\d{4}\/\d{1,2}\/\d{1,2}$/.test(s)) {
    const parts = s.split(/[-/]/)
    return parts[0] + '-' + ('0' + parts[1]).slice(-2) + '-' + ('0' + parts[2]).slice(-2)
  }
  if (/^\d{1,3}$/.test(s)) return ''
  return s
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
  editForm.value = { name: u.name || '', gender: String(u.gender == null ? 0 : u.gender), age: toDateValue(u.age), prefix: u.prefix || '', intro: u.intro || '' }
  pendingAvatar.value = ''
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
    age: editForm.value.age.trim(),
    prefix: editForm.value.prefix.trim(),
    intro: editForm.value.intro.trim(),
  }
  if (pendingAvatar.value) body.avatar = pendingAvatar.value
  apiFetch('/api/user/info', { method: 'PUT', body }).then((d) => {
    if (!d) return
    if (d.success) { toast('资料已更新'); location.reload() }
    else { editError.value = d.message || '保存失败'; editErrorColor.value = '' }
  })
}
function toggleFav() { favCollapsed.value = !favCollapsed.value }

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
          <div class="user-profile-name">{{ user.name }} <span v-if="user.prefix" class="tag">{{ user.prefix }}</span></div>
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
          <h3><i class="fa fa-user"></i> 编辑资料</h3>
          <button class="modal-close" @click="closeEdit">&times;</button>
        </div>
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
          <label>年龄（生日）</label>
          <input v-model="editForm.age" type="date" max="2100-12-31">
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
        <div class="modal-actions">
          <button class="btn btn-outline" @click="closeEdit">取消</button>
          <button class="btn btn-primary" @click="saveEdit">保存</button>
        </div>
      </div>
    </div>
  </div>
</template>
