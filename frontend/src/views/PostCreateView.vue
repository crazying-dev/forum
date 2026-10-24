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
        <!-- 公告组件①：发帖须知（合规提示，对照 V1 .post-compliance-notice） -->
        <div class="post-compliance-notice">
          <div class="post-compliance-header">
            <i class="fa fa-shield"></i>
            <span>发帖须知</span>
          </div>
          <ul class="post-compliance-list">
            <li>遵守中华人民共和国相关法律法规，不得发布违法违规内容</li>
            <li>禁止涉及政治敏感、涉黄涉暴、血腥恐怖、毒品赌博等内容</li>
            <li>禁止人身攻击、谩骂侮辱、恶意引战、网络暴力等行为</li>
            <li>禁止发布广告、spam、外链刷量、引流等垃圾信息</li>
            <li>禁止泄露他人或自己的隐私信息（真实姓名、电话、地址等）</li>
            <li>禁止侵犯他人知识产权，转载请注明出处或获得授权</li>
            <li>内容应与论坛主题（罗小黑战记及二次元文化）相关，鼓励友善交流</li>
            <li>违反以上规定的帖子将被删除，情节严重者将封禁账号</li>
          </ul>
        </div>

        <div class="form-group">
          <label>标题</label>
          <input v-model="title" type="text" maxlength="100" placeholder="标题（最多 100 字）">
        </div>
        <div class="form-group">
          <label>分类</label>
          <select v-model="category">
            <option value="general">综合</option>
            <option value="talk">闲聊</option>
            <option value="question">求助</option>
            <option value="share">分享</option>
            <option value="creative">创作</option>
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
