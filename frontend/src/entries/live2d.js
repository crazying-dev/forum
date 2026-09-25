import { createApp } from 'vue'
import { initAuth } from '../utils.js'
import Live2DView from '../views/Live2DView.vue'

initAuth().then(() => {
  createApp(Live2DView).mount('#app')
})
