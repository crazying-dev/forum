// 用户主页：Vue3 挂载入口（登录态就绪后再挂载，isSelf/收藏/评论依赖 currentUser）
import { createApp } from 'vue'
import { initAuth } from '../utils.js'
import UserView from '../views/UserView.vue'

initAuth().then(() => {
  createApp(UserView).mount('#app')
})
