// 首页：Vue3 挂载入口（登录态就绪后再挂载，收藏区需要 currentUser）
import { createApp } from 'vue'
import { initAuth } from '../utils.js'
import HomeView from '../views/HomeView.vue'

initAuth().then(() => {
  createApp(HomeView).mount('#app')
})
