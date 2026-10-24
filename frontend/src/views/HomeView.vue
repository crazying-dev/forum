<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import PostList from '../components/PostList.vue'
import { apiFetch, getCurrentUser } from '../utils.js'

// 排序模式：random（随机推荐）/ time（时间顺序）/ comprehensive（综合排序）
const sorts = [
  { key: 'random', label: '随机推荐', icon: 'fa-random', url: '/api/posts/random?limit=200' },
  { key: 'time', label: '时间顺序', icon: 'fa-clock-o', url: '/api/posts?sort=time&page_size=100' },
  { key: 'comprehensive', label: '综合排序', icon: 'fa-fire', url: '/api/posts?sort=comprehensive&page_size=100' },
]
const sortKey = ref('random')
const sortOpen = ref(false)
const posts = ref([])
const loading = ref(true)
// 换一批：5 秒冷却（刷新锁定期间禁用按钮，拦截重复点击）
const refreshLocked = ref(false)
// 我的收藏
const favPosts = ref([])
const favLoaded = ref(false)
const favCollapsed = ref(false)

const user = getCurrentUser()
const sortInfo = computed(() => sorts.find((s) => s.key === sortKey.value) || sorts[0])

function loadHome() {
  loading.value = true
  apiFetch(sortInfo.value.url).then((d) => {
    loading.value = false
    posts.value = (d && d.success) ? (d.posts || []) : []
  }).catch(() => {
    loading.value = false
    posts.value = []
  })
}
function switchSort(key) {
  sortKey.value = key
  sortOpen.value = false
  loadHome()
}
function refresh() {
  if (refreshLocked.value) return
  refreshLocked.value = true
  loadHome()
  setTimeout(() => { refreshLocked.value = false }, 5000)
}
function loadFavs() {
  if (favLoaded.value || !user) return
  favLoaded.value = true
  apiFetch('/api/user/' + user.id + '/favorites').then((d) => {
    if (d && d.success) favPosts.value = d.posts || []
  }).catch(() => {})
}
function toggleFav() { favCollapsed.value = !favCollapsed.value }
function onDocClick() { sortOpen.value = false }

onMounted(() => {
  loadHome()
  loadFavs()
  document.addEventListener('click', onDocClick)
})
onBeforeUnmount(() => document.removeEventListener('click', onDocClick))
</script>

<template>
  <div class="page">
    <section class="card home-hero">
      <h1 class="home-hero-title">妖精论坛</h1>
      <p class="home-hero-sub">分享你的想法与故事</p>
      <div class="home-hero-actions">
        <a href="/forum" class="btn btn-primary"><i class="fa fa-list"></i> 论坛广场</a>
        <a href="/post/create" class="btn btn-outline"><i class="fa fa-pencil"></i> 发布帖子</a>
      </div>
    </section>

    <section v-if="favLoaded && favPosts.length" class="card">
      <div class="card-header">
        <h2 class="card-title"><i class="fa fa-bookmark"></i> 我的收藏</h2>
        <button class="btn btn-sm" @click="toggleFav">
          <i :class="favCollapsed ? 'fa fa-angle-down' : 'fa fa-angle-up'"></i> {{ favCollapsed ? '展开' : '收起' }}
        </button>
      </div>
      <div v-show="!favCollapsed">
        <PostList :posts="favPosts" :loading="false" empty-text="暂无收藏" />
      </div>
    </section>

    <section class="card">
      <div class="card-header">
        <div class="home-sort">
          <button type="button" class="home-sort-toggle" @click.stop="sortOpen = !sortOpen">
            <i :class="'fa ' + sortInfo.icon"></i>
            <span>{{ sortInfo.label }}</span>
            <i class="fa fa-caret-down"></i>
          </button>
          <div class="home-sort-menu" :class="{ open: sortOpen }">
            <button
              v-for="s in sorts"
              :key="s.key"
              type="button"
              class="home-sort-item"
              :class="{ active: sortKey === s.key }"
              @click="switchSort(s.key)"
            >
              <i :class="'fa ' + s.icon"></i> {{ s.label }}
            </button>
          </div>
        </div>
        <button class="btn btn-sm" :class="{ disabled: refreshLocked }" :disabled="refreshLocked" @click="refresh">
          <i class="fa fa-refresh"></i> 换一批
        </button>
      </div>
      <PostList :posts="posts" :loading="loading" empty-text="暂无帖子" />
    </section>
  </div>
</template>
