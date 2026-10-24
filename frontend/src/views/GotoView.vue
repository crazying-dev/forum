<script setup>
import { computed, ref } from 'vue'

// 后端通过挂载点 data-goto-target 传入目标 URL（tojson 序列化）
const raw = ref('')
try {
  const node = document.getElementById('app')
  raw.value = node && node.dataset.gotoTarget ? JSON.parse(node.dataset.gotoTarget) : ''
} catch (e) { raw.value = '' }
const target = ref(String(raw.value || '').trim())

// 仅允许 http/https 协议，防止 javascript:/data: 等协议绕过
const isHttp = computed(() => /^https?:\/\//i.test(target.value))
const showConfirm = computed(() => !!target.value && isHttp.value)
const display = computed(() => target.value ? target.value : '（未提供跳转目标）')
</script>

<template>
  <div class="goto-container">
    <div class="goto-card">
      <div class="goto-icon"><i class="fa fa-exclamation-triangle"></i></div>
      <h2>即将离开妖精论坛</h2>
      <p class="goto-tip">无法验证以下链接的安全性，是否确认跳转？</p>
      <div class="goto-url">{{ display }}</div>
      <div class="goto-actions">
        <button class="goto-btn goto-btn-cancel" @click="history.back()">
          <i class="fa fa-arrow-left"></i> 返回上一页
        </button>
        <a
          v-if="showConfirm"
          class="goto-btn goto-btn-confirm"
          :href="target"
          rel="nofollow noopener noreferrer"
          target="_blank"
        >
          <i class="fa fa-external-link"></i> 继续访问
        </a>
      </div>
      <p class="goto-warn">提示：该链接由用户发布，请注意防范钓鱼、诈骗等风险。</p>
    </div>
  </div>
</template>
