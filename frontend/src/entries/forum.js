// 论坛广场页：Vue3 挂载入口（登录态就绪后再挂载，与旧版 initAuth().then(route) 时序一致）
import { createApp } from 'vue'
import { initAuth } from '../utils.js'
import ForumView from '../views/ForumView.vue'

initAuth().then(() => {
  createApp(ForumView).mount('#app')
})
