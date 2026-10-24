import { createApp } from 'vue'
import { initAuth } from '../utils.js'
import VerifyFailedView from '../views/VerifyFailedView.vue'

initAuth().then(() => {
  createApp(VerifyFailedView).mount('#app')
})
