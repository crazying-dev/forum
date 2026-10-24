<script setup>
import { nextTick, onMounted, ref } from 'vue'
import { enhanceContent, renderMarkdown } from '../utils.js'

const BASE = '/static/mouse/Liunx/'
const markdownHtml = ref('')
const licenseText = ref('')
const markdownBox = ref(null)

function loadLang() {
  const lang = (new URLSearchParams(location.search).get('l') || '').toUpperCase()
  return lang === 'EN' ? 'README_en-US.md' : 'README.md'
}

onMounted(() => {
  fetch(BASE + loadLang())
    .then((r) => r.text())
    .then((text) => {
      markdownHtml.value = renderMarkdown(text)
      return nextTick()
    })
    .then(() => { if (markdownBox.value) enhanceContent(markdownBox.value) })
    .catch(() => { markdownHtml.value = '<p class="wiki-intro">README 加载失败，请稍后重试。</p>' })
  fetch(BASE + 'LICENSE')
    .then((r) => r.text())
    .then((text) => { licenseText.value = text })
    .catch(() => { licenseText.value = 'LICENSE 加载失败' })
})
</script>

<template>
  <div class="wiki-page mouse-linux-page">
    <div class="wiki-header">
      <h2>罗小黑战记鼠标 - Linux版</h2>
      <p class="wiki-intro" style="color:red;">未经授权禁止商用！！</p>
    </div>

    <div class="wiki-container">
      <div class="mouse-linux-download">
        <a href="/static/mouse/Liunx/罗小黑战记鼠标Linux版.zip" class="wiki-card" download>
          <div class="wiki-card-content">
            <i class="fa fa-download"></i>
            <h3>下载鼠标包</h3>
            <p>罗小黑战记鼠标 Linux版.zip</p>
          </div>
        </a>
      </div>

      <div ref="markdownBox" class="markdown-body mouse-linux-markdown" v-html="markdownHtml"></div>

      <details class="mouse-linux-license">
        <summary>LICENSE</summary>
        <pre>{{ licenseText }}</pre>
      </details>
    </div>
  </div>
</template>
