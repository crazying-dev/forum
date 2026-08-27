import { createApp } from 'vue'
import { initAuth } from '../utils.js'
import VerifySuccessView from '../views/VerifySuccessView.vue'

initAuth().then(() => {
  createApp(VerifySuccessView).mount('#app')
})
