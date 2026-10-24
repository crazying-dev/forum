<script setup>
import { computed } from 'vue'
import { avatarHtml, categoryLabel, esc, fmtTime } from '../utils.js'

const props = defineProps({
  post: { type: Object, required: true },
})

const p = computed(() => props.post || {})
// 作者行：头像延迟加载（data-src）+ 用户名（保持与旧版 postItemHtml 相同的结构与样式类）
const authorHtml = computed(() => {
  const post = p.value
  return avatarHtml(post.user_avatar) +
    ' <a class="link-user" href="/users/' + esc(post.user_id) + '">' + esc(post.user_name) + '</a>'
})
</script>

<template>
  <div
    class="post-item"
    :data-pid="p.id"
    :data-uid="p.user_id"
    :data-post-link="'/post/' + p.id"
  >
    <a class="post-item-title" :href="'/post/' + p.id">{{ p.title }}</a>
    <div class="post-item-summary">{{ p.summary || '' }}</div>
    <div class="post-item-meta">
      <span class="tag">{{ categoryLabel(p.category) }}</span>
      <span v-html="authorHtml"></span>
      <span><i class="fa fa-thumbs-o-up"></i> {{ p.likes || 0 }}</span>
      <span><i class="fa fa-eye"></i> {{ p.views || 0 }}</span>
      <span>{{ fmtTime(p.created_at) }}</span>
    </div>
  </div>
</template>
