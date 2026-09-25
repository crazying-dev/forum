<script setup>
import { onBeforeUnmount, onMounted } from 'vue'

// Live2D 模型加载由 AfterBody.js 的 initLive2D 负责（路由数据等由模板渲染后执行）
// Vue 挂载完成后调用，此时 canvas / 进度条 DOM 已就绪
function startLive2D() {
  const app = window.__yoyoApp || {}
  if (typeof app.initLive2D === 'function') app.initLive2D()
}

onMounted(() => { startLive2D() })
onBeforeUnmount(() => {
  // 离开页面时清理全局 Live2D 实例，避免影响其他页面
  const app = window.__yoyoApp || {}
  if (typeof app.destroyLive2D === 'function') app.destroyLive2D()
})
</script>

<template>
  <div class="page live2d-page">
    <div class="card">
      <div class="wiki-header">
        <h2>罗小黑Live2D模型</h2>
        <h6 style="color:red;">不可下载，仅供展示</h6>
      </div>

      <div class="live2d-author-card">
        <div class="live2d-author-label">Live2D 模型原作者</div>
        <div class="live2d-author-info">
          <i class="fa fa-paint-brush live2d-author-icon"></i>
          <div class="live2d-author-text">
            <span class="live2d-author-name">@盒装现烤奕潞</span>
            <span class="live2d-author-desc">在小红书收获了199.2K次赞与收藏</span>
          </div>
        </div>
        <a href="https://xhslink.com/m/7kf365dQt3n" target="_blank" rel="noopener noreferrer" class="live2d-author-link">
          查看Ta的主页 <i class="fa fa-arrow-right"></i>
        </a>
      </div>

      <div class="live2d-container">
        <div id="live2d-canvas-wrapper" class="live2d-canvas-wrapper">
          <canvas id="live2d-canvas" class="live2d-canvas"></canvas>
          <div class="live2d-loading" id="live2d-loading">
            <div class="live2d-progress-container">
              <div class="live2d-progress-bar">
                <div class="live2d-progress-fill" id="live2d-progress-fill"></div>
              </div>
              <div class="live2d-progress-text" id="live2d-progress-text">初始化...</div>
              <div class="live2d-progress-percent" id="live2d-progress-percent">0%</div>
            </div>
          </div>
          <div class="live2d-error" id="live2d-error" style="display:none;">
            <i class="fa fa-exclamation-triangle"></i>
            <span>加载失败，请刷新重试</span>
          </div>
        </div>
      </div>

      <div class="live2d-actions-section">
        <h3 class="live2d-actions-title">动作示例</h3>
        <div class="live2d-actions-grid">
          <div v-for="g in gifs" :key="g.name" class="live2d-action-card">
            <div class="live2d-action-gif">
              <img :src="'/static/live2d/gif/' + g.name + '.gif'" :alt="g.name" loading="lazy" decoding="async">
            </div>
            <span class="live2d-action-name">{{ g.name }}</span>
          </div>
        </div>
      </div>

      <div class="wiki-footer">
        <p>点击模型可以互动哦~</p>
      </div>
    </div>
  </div>
</template>

<script>
// 动作 GIF 列表
export default {
  data() { return { gifs: [{ name: '待机' }, { name: '嘿咻' }, { name: '惊醒' }, { name: '起跳' }, { name: '铁片' }] } },
}
</script>
