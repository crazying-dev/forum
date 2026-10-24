// 帖子详情页：Vue3 挂载入口（登录态就绪后再挂载，作者按钮/关注按钮依赖 currentUser）
import { createApp } from 'vue'
import { initAuth } from '../utils.js'
import PostDetailView from '../views/PostDetailView.vue'

initAuth().then(() => {
  createApp(PostDetailView).mount('#app')
})
