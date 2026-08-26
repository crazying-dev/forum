<script setup>
import { computed, ref } from 'vue'
import { avatarHtml, fmtTime } from '../utils.js'

const props = defineProps({
  comment: { type: Object, required: true },
  me: { type: Object, default: null },
  postLink: { type: String, default: '' },
})
const emit = defineEmits(['reply', 'delete'])

const folded = ref(false)
const kids = computed(() => props.comment.children || [])
function onDelete() {
  if (!confirm('确定删除该评论？')) return
  emit('delete', props.comment.id)
}
</script>

<template>
  <div
    class="comment-item"
    :class="{ 'comment-child': comment.parent_id }"
    :data-cid="comment.id"
    :data-cuid="comment.user_id"
    :data-post-link="postLink"
  >
    <span v-html="avatarHtml(comment.user_avatar)"></span>
    <div class="comment-body">
      <div class="comment-head">
        <a :href="'/users/' + comment.user_id">{{ comment.user_name }}</a>
        <span v-if="comment.parent_id" class="comment-reply-to">回复</span>
        <span> · {{ fmtTime(comment.created_at) }}</span>
      </div>
      <div class="comment-content">{{ comment.content }}</div>
      <div class="comment-actions">
        <button class="comment-reply" @click="emit('reply', { id: comment.id, name: comment.user_name })">回复</button>
        <button v-if="me && me.id === comment.user_id" class="comment-reply" @click="onDelete">删除</button>
      </div>
    </div>
    <template v-if="kids.length">
      <div v-show="!folded" class="comment-children" :data-parent="comment.id">
        <CommentItem
          v-for="k in kids"
          :key="k.id"
          :comment="k"
          :me="me"
          :post-link="postLink"
          @reply="emit('reply', $event)"
          @delete="emit('delete', $event)"
        />
      </div>
      <button class="comment-fold" @click="folded = !folded">
        {{ folded ? '展开回复 (' + kids.length + ')' : '收起回复' }}
      </button>
    </template>
  </div>
</template>
