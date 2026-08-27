import { createApp } from 'vue'
import { initAuth } from '../utils.js'
import WikiPersonalView from '../views/WikiPersonalView.vue'

initAuth().then(() => {
  createApp(WikiPersonalView).mount('#app')
})
