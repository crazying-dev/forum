import { createApp } from 'vue'
import { initAuth } from '../utils.js'
import MouseView from '../views/MouseView.vue'

initAuth().then(() => {
  createApp(MouseView).mount('#app')
})
