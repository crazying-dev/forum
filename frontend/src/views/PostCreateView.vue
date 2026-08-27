<script setup>
import { nextTick, ref } from 'vue'
import { apiFetch, enhanceContent, needLogin, renderMarkdown } from '../utils.js'

const title = ref('')
const category = ref('general')
const content = ref('')
const mode = ref('edit')
const previewHtml = ref('')
const error = ref('')
const submitting = ref(false)
const previewBox = ref(null)

needLogin()

function switchMode(m) {
  mode.value = m
  if (m === 'preview') {
    previewHtml.value = content.value ? renderMarkdown(content.value) : '<p style="color:var(--color-text-tertiary)">（空）</p>'
    nextTick(() => { if (previewBox.value) enhanceContent(previewBox.value) })
  }
}

async function submit() {
  if (submitting.value) return
  if (!title.value.trim() || !content.value.trim()) { error.value = '标题和内容不能为空'; return }
  submitting.value = true
  error.value = ''
  const d = await apiFetch('/api/posts/create', {
    method: 'POST',
    body: { title: title.value.trim(), content: content.value.trim(), category: category.value },
  }).catch(() => null)
  submitting.value = false
  if (!d) { error.value = '发布失败'; return }
  if (d.success) location.href = '/post/' + d.id
  else error.value = d.message || '发布失败'
}
</script>

<template>
  <div class="page">
    <div class="card">
      <div class="card-header">
        <h2 class="card-title"><i class="fa fa-pencil"></i> 发布帖子</h2>
      </div>
      <form @submit.prevent="submit">
        <div class="form-group">
          <label>标题</label>
          <input v-model="title" type="text" maxlength="100" placeholder="标题（最多 100 字）">
        </div>
        <div class="form-group">
          <label>分类</label>
          <select v-model="category">
            <option value="general">综合</option>
            <option value="叶羽">叶羽</option>
            <option value="创意">创意</option>
            <option value="求助">求助</option>
          </select>
        </div>
        <div class="form-group">
          <label>内容</label>
          <div class="editor-tabs">
            <button type="button" class="editor-tab" :class="{ active: mode === 'edit' }" @click="switchMode('edit')">编辑</button>
            <button type="button" class="editor-tab" :class="{ active: mode === 'preview' }" @click="switchMode('preview')">预览</button>
          </div>
          <textarea v-show="mode === 'edit'" v-model="content" rows="12" placeholder="支持 Markdown 格式内容"></textarea>
          <div v-show="mode === 'preview'" ref="previewBox" class="editor-preview markdown-body" v-html="previewHtml"></div>
        </div>
        <p class="auth-error" v-if="error">{{ error }}</p>
        <button type="submit" class="btn btn-primary" :disabled="submitting">发布</button>
      </form>
    </div>
  </div>
</template>
