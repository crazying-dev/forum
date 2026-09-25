import { createApp } from 'vue'
import { initAuth } from '../utils.js'
import WikiView from '../views/WikiView.vue'

initAuth().then(() => {
  createApp(WikiView).mount('#app')
})
