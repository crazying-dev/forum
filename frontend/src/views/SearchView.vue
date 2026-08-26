<script setup>
import { computed, onMounted, ref } from 'vue'
import PostCard from '../components/PostCard.vue'
import { apiFetch, avatarHtml, esc, resolveAvatars } from '../utils.js'

const params = new URLSearchParams(location.search)
const keyword = ref(params.get('k') || '')
const types = [
  { key: 'both', label: '全部' },
  { key: 'posts', label: '帖子' },
  { key: 'users', label: '用户' },
]
const type = ref('both')
const page = ref(1)
const loading = ref(true)
const loadingMore = ref(false)
const posts = ref([])
const users = ref([])
const postsTotal = ref(0)
const usersTotal = ref(0)
const hasMore = ref(false)

const keywordLabel = computed(() => (keyword.value ? '「' + keyword.value + '」' : ''))

async function load(reset) {
  if (reset) { page.value = 1; posts.value = []; users.value = []; loading.value = true }
  const url = '/api/search?k=' + encodeURIComponent(keyword.value) +
    '&type=' + type.value + '&page=' + page.value + '&page_size=20'
  const d = await apiFetch(url).catch(() => null)
  loading.value = false
  loadingMore.value = false
  if (!d || !d.success) return
  if (type.value !== 'users' && d.posts) {
    postsTotal.value = d.posts_total || 0
    posts.value = reset ? (d.posts || []) : posts.value.concat(d.posts || [])
  }
  if (type.value !== 'posts' && d.users) {
    usersTotal.value = d.users_total || 0
    users.value = reset ? (d.users || []) : users.value.concat(d.users || [])
  }
  hasMore.value = (type.value !== 'users' && !!d.posts_has_more) || (type.value !== 'posts' && !!d.users_has_more)
  await nextTick()
  resolveAvatars(document)
}
function switchType(key) {
  if (type.value === key) return
  type.value = key
  load(true)
}
function loadMore() {
  if (!hasMore.value || loadingMore.value) return
  loadingMore.value = true
  page.value++
  load(false)
}

onMounted(() => { if (keyword.value) load(true); else loading.value = false })
</script>

<template>
  <div class="page">
    <div class="card">
      <div class="card-header">
        <h2 class="card-title"><i class="fa fa-search"></i> 搜索 <span>{{ keywordLabel }}</span></h2>
      </div>
      <div class="search-type-tabs">
        <button
          v-for="t in types"
          :key="t.key"
          class="tab"
          :class="{ active: type === t.key }"
          @click="switchType(t.key)"
        >{{ t.label }}</button>
      </div>
      <div class="search-result">
        <div v-if="loading" class="empty">加载中...</div>
        <template v-else>
          <template v-if="type !== 'users'">
            <div class="card-title" style="margin:8px 0;">帖子（{{ postsTotal }}）</div>
            <div v-if="posts.length">
              <PostCard v-for="p in posts" :key="p.id" :post="p" />
            </div>
            <div v-else class="empty">无相关帖子</div>
          </template>
          <template v-if="type !== 'posts'">
            <div class="card-title" style="margin:8px 0;">用户（{{ usersTotal }}）</div>
            <div v-if="users.length">
              <div v-for="u in users" :key="u.id" class="post-item">
                <span v-html="avatarHtml(u.avatar)"></span>
                <a class="link-user" :href="'/users/' + esc(u.id)">{{ u.name }}</a>
                <span v-if="u.prefix" class="tag" style="margin-left:6px;">{{ u.prefix }}</span>
              </div>
            </div>
            <div v-else class="empty">无相关用户</div>
          </template>
          <div v-if="!posts.length && !users.length" class="empty">无结果</div>
        </template>
      </div>
      <div v-if="hasMore" class="load-more">
        <button class="btn btn-outline" :disabled="loadingMore" @click="loadMore">
          {{ loadingMore ? '加载中...' : '加载更多' }}
        </button>
      </div>
    </div>
  </div>
</template>
