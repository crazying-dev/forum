import { createApp } from 'vue'
import { initAuth } from '../utils.js'
import PostCreateView from '../views/PostCreateView.vue'

initAuth().then(() => {
  createApp(PostCreateView).mount('#app')
})
