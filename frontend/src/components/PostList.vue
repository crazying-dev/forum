<script setup>
import { nextTick, watch } from 'vue'
import PostCard from './PostCard.vue'
import { resolveAvatars } from '../utils.js'

const props = defineProps({
  posts: { type: Array, default: () => [] },
  loading: { type: Boolean, default: false },
  loadingMore: { type: Boolean, default: false },
  hasMore: { type: Boolean, default: false },
  emptyText: { type: String, default: '暂无帖子' },
})

const emit = defineEmits(['load-more'])

// 列表渲染完成后触发头像延迟加载（真实 URL 从 data-src 注入到 src）
// flush:post + immediate 覆盖：首次挂载、追加加载、v-if 条件挂载等所有渲染时机
watch(
  () => props.posts,
  async () => {
    await nextTick()
    resolveAvatars(document)
  },
  { immediate: true, flush: 'post' }
)
</script>

<template>
  <div class="post-list">
    <div v-if="loading" class="empty">加载中...</div>
    <template v-else-if="posts.length">
      <PostCard v-for="p in posts" :key="p.id" :post="p" />
      <div v-if="hasMore" class="load-more">
        <button class="btn btn-outline" :disabled="loadingMore" @click="emit('load-more')">
          {{ loadingMore ? '加载中...' : '加载更多' }}
        </button>
      </div>
    </template>
    <div v-else class="empty">{{ emptyText }}</div>
  </div>
</template>
