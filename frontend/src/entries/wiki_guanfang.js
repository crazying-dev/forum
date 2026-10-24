import { createApp } from 'vue'
import { initAuth } from '../utils.js'
import WikiGuanfangView from '../views/WikiGuanfangView.vue'

initAuth().then(() => {
  createApp(WikiGuanfangView).mount('#app')
})
