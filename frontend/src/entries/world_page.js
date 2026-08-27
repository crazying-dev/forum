import { createApp } from 'vue'
import { initAuth } from '../utils.js'
import WorldPageView from '../views/WorldPageView.vue'

initAuth().then(() => {
  createApp(WorldPageView).mount('#app')
})
