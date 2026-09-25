import { createApp } from 'vue'
import { initAuth } from '../utils.js'
import PrivacyView from '../views/PrivacyView.vue'

initAuth().then(() => {
  createApp(PrivacyView).mount('#app')
})
