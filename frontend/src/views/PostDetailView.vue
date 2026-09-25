<script setup>
import { computed, nextTick, onMounted, ref } from 'vue'
import CommentItem from '../components/CommentItem.vue'
import {
  apiFetch, avatarHtml, categoryLabel, enhanceContent, fmtTime,
  getCurrentUser, needLogin, openReportModal, renderMarkdown, resolveAvatars, toast,
} from '../utils.js'

const postId = computed(() => {
  const m = location.pathname.match(/^\/post\/([^/]+)/)
  return m ? decodeURIComponent(m[1]) : ''
})
const loading = ref(true)
const notFound = ref(false)
const post = ref(null)
const comments = ref([])
const liked = ref(false)
const favorited = ref(false)
const followText = ref('关注')
const showFollow = ref(false)
const replyTarget = ref(null)
const commentText = ref('')

const me = getCurrentUser()
const postLink = computed(() => location.pathname + location.search)
const commentCount = computed(() => comments.value.length)
// 评论楼中楼：按 parent_id 构建树
const commentTree = computed(() => {
  const map = {}
  comments.value.forEach((c) => { map[c.id] = c; c.children = [] })
  const roots = []
  comments.value.forEach((c) => {
    if (c.parent_id && map[c.parent_id]) map[c.parent_id].children.push(c)
    else roots.push(c)
  })
  return roots
})

async function load() {
  if (!postId.value) { loading.value = false; notFound.value = true; return }
  const d = await apiFetch('/api/posts/' + encodeURIComponent(postId.value))
  loading.value = false
  if (!d || !d.success) { notFound.value = true; return }
  post.value = d.post
  liked.value = !!d.liked
  favorited.value = !!d.favorited
  comments.value = d.comments || []
  if (me && me.id !== post.value.user_id) {
    showFollow.value = true
    apiFetch('/api/user/' + encodeURIComponent(post.value.user_id)).then((r) => {
      if (r && r.success) followText.value = (r.user && r.user.is_following) ? '已关注' : '关注'
    }).catch(() => {})
  }
  await nextTick()
  resolveAvatars(document)
  enhanceContent(document.querySelector('.post-detail-content'))
  // 从个人主页带 #comment-<id> 跳转而来：滚动定位并高亮
  const h = location.hash || ''
  if (h.indexOf('#comment-') === 0) {
    const target = document.querySelector('.comment-item[data-cid="' + h.slice(9) + '"]')
    if (target) {
      setTimeout(() => {
        target.scrollIntoView({ behavior: 'smooth', block: 'center' })
        target.classList.add('highlight-comment')
      }, 120)
    }
  }
}

function doLike() {
  if (!needLogin()) return
  apiFetch('/api/posts/' + postId.value + '/like', { method: 'POST' }).then((d) => {
    if (!d) return
    liked.value = !!d.liked
    if (post.value) post.value.likes = d.likes
  })
}
function doFav() {
  if (!needLogin()) return
  apiFetch('/api/posts/' + postId.value + '/favorite', { method: 'POST' }).then((d) => {
    if (d) favorited.value = !!d.favorited
  })
}
function doShare() {
  const url = location.href
  ;(navigator.clipboard ? navigator.clipboard.writeText(url) : Promise.reject())
    .then(() => toast('链接已复制'))
    .catch(() => toast('当前浏览器不支持一键复制'))
}
function doReport() {
  if (!needLogin()) return
  openReportModal('post', postId.value)
}
function doDelete() {
  if (!confirm('确定删除该帖子？')) return
  apiFetch('/api/posts/' + postId.value + '/delete', { method: 'POST' }).then((d) => {
    if (d && d.success) location.href = '/forum'
    else if (d) toast(d.message || '删除失败')
  })
}
function toggleFollow() {
  if (!needLogin()) return
  apiFetch('/api/user/' + encodeURIComponent(post.value.user_id) + '/follow', { method: 'POST' }).then((r) => {
    if (r) {
      followText.value = r.following ? '已关注' : '关注'
      toast(r.following ? '已关注作者' : '已取消关注')
    }
  })
}
function startReply({ id, name }) {
  replyTarget.value = { id, name }
  const ta = document.getElementById('commentContent')
  if (ta) ta.focus()
}
function cancelReply() { replyTarget.value = null }
function submitComment() {
  if (!needLogin()) return
  const content = commentText.value.trim()
  if (!content) return
  const body = { content }
  if (replyTarget.value) body.parent_id = replyTarget.value.id
  apiFetch('/api/posts/' + postId.value + '/comments/create', { method: 'POST', body }).then((d) => {
    if (d && d.success) location.reload()
  })
}
function deleteComment(cid) {
  apiFetch('/api/comments/' + cid + '/delete', { method: 'POST' }).then((d) => {
    if (d && d.success) location.reload()
  })
}

onMounted(load)
</script>

<template>
  <div class="page">
    <div v-if="loading" class="card"><div class="empty">加载中...</div></div>
    <div v-else-if="notFound" class="card"><div class="empty">帖子不存在</div></div>
    <template v-else>
      <div class="card">
        <h1 class="post-detail-title">{{ post.title }}</h1>
        <div class="post-detail-meta">
          <span v-html="avatarHtml(post.user_avatar, 'avatar-sm')"></span>
          <a class="link-user" :href="'/users/' + post.user_id">{{ post.user_name }}</a>
          <button v-if="showFollow" class="btn btn-sm btn-outline" @click="toggleFollow">{{ followText }}</button>
          <span class="tag">{{ categoryLabel(post.category) }}</span>
          <span><i class="fa fa-eye"></i> {{ post.views || 0 }}</span>
          <span><i class="fa fa-thumbs-o-up"></i> {{ post.likes || 0 }}</span>
          <span>{{ fmtTime(post.created_at) }}</span>
        </div>
        <div class="post-detail-content markdown-body" v-html="renderMarkdown(post.content)"></div>
        <div class="post-actions">
          <button class="btn btn-sm action-btn" :class="{ liked }" @click="doLike">
            <i class="fa fa-thumbs-o-up"></i> 点赞 <span>{{ post.likes || 0 }}</span>
          </button>
          <button class="btn btn-sm action-btn" @click="doFav">
            <i class="fa fa-bookmark-o"></i> {{ favorited ? '已收藏' : '收藏' }}
          </button>
          <button class="btn btn-sm action-btn" @click="doShare"><i class="fa fa-share-alt"></i> 分享</button>
          <button class="btn btn-sm btn-outline action-btn" @click="doReport"><i class="fa fa-flag-o"></i> 举报</button>
          <button v-if="me && me.id === post.user_id" class="btn btn-sm btn-outline action-btn" @click="doDelete">
            <i class="fa fa-trash-o"></i> 删除
          </button>
        </div>
      </div>
      <div class="card">
        <div class="card-header">
          <h2 class="card-title"><i class="fa fa-comments"></i> 评论 <span>({{ commentCount }})</span></h2>
        </div>
        <div v-if="!comments.length" class="empty">暂无评论</div>
        <div v-else class="comment-list">
          <CommentItem
            v-for="c in commentTree"
            :key="c.id"
            :comment="c"
            :me="me"
            :post-link="postLink"
            @reply="startReply"
            @delete="deleteComment"
          />
        </div>
        <div class="comment-input">
          <div v-if="replyTarget" class="reply-bar">
            <span>回复 @{{ replyTarget.name }}：</span>
            <button type="button" @click="cancelReply">取消回复</button>
          </div>
          <textarea id="commentContent" v-model="commentText" rows="2" maxlength="500" placeholder="写下你的评论..."></textarea>
          <button class="btn btn-primary" @click="submitComment">发表评论</button>
        </div>
      </div>
    </template>
  </div>
</template>
