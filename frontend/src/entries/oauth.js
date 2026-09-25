import { createApp } from 'vue'
import { initAuth } from '../utils.js'
import OAuthView from '../views/OAuthView.vue'

initAuth().then(() => {
  createApp(OAuthView).mount('#app')
})
