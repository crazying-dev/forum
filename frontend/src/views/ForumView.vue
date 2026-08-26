<script setup>
import { onMounted, ref } from 'vue'
import PostList from '../components/PostList.vue'
import { apiFetch } from '../utils.js'

const categories = [
  { key: '', label: '全部' },
  { key: 'general', label: '综合' },
  { key: '叶羽', label: '叶羽' },
  { key: '创意', label: '创意' },
  { key: '求助', label: '求助' },
]
const current = ref('')
const posts = ref([])
const page = ref(1)
const loading = ref(true)
const loadingMore = ref(false)
const hasMore = ref(true)

function load(reset) {
  if (reset) {
    page.value = 1
    posts.value = []
    loading.value = true
  }
  const url = '/api/posts?page=' + page.value + '&page_size=20' +
    (current.value ? '&category=' + encodeURIComponent(current.value) : '')
  return apiFetch(url).then((d) => {
    if (!d || !d.success) {
      if (reset) { loading.value = false; posts.value = [] }
      return
    }
    const arr = d.posts || []
    posts.value = reset ? arr : posts.value.concat(arr)
    hasMore.value = arr.length >= 20
    loading.value = false
    loadingMore.value = false
  }).catch(() => {
    loading.value = false
    loadingMore.value = false
    if (reset) posts.value = []
  })
}

function selectCategory(key) {
  if (current.value === key) return
  current.value = key
  load(true)
}
function loadMore() {
  if (!hasMore.value || loadingMore.value) return
  loadingMore.value = true
  page.value++
  load(false)
}

onMounted(() => { load(true) })
</script>

<template>
  <div class="page">
    <div class="card">
      <div class="card-header">
        <h2 class="card-title"><i class="fa fa-list"></i> 论坛广场</h2>
        <a href="/post/create" class="btn btn-primary btn-sm"><i class="fa fa-pencil"></i> 发布帖子</a>
      </div>
      <div class="category-tabs">
        <button
          v-for="c in categories"
          :key="c.key"
          class="tab"
          :class="{ active: current === c.key }"
          @click="selectCategory(c.key)"
        >{{ c.label }}</button>
      </div>
      <PostList
        :posts="posts"
        :loading="loading"
        :loading-more="loadingMore"
        :has-more="hasMore"
        empty-text="暂无帖子"
        @load-more="loadMore"
      />
    </div>
  </div>
</template>
