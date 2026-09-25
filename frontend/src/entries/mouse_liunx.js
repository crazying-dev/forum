import { createApp } from 'vue'
import { initAuth } from '../utils.js'
import MouseLinuxView from '../views/MouseLinuxView.vue'

initAuth().then(() => {
  createApp(MouseLinuxView).mount('#app')
})
