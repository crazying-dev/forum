import { createApp } from 'vue'
import { initAuth } from '../utils.js'
import GotoView from '../views/GotoView.vue'

initAuth().then(() => {
  createApp(GotoView).mount('#app')
})
