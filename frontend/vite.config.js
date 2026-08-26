// 妖精论坛 V2 前端构建：多入口渐进式 Vue3，产物输出到 ../static/vue/（Flask 直接托管）
import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import { fileURLToPath, URL } from 'node:url'

export default defineConfig({
  plugins: [vue()],
  build: {
    // 输出到 Flask 静态目录（模板用 ?v={{ static_version }} 做缓存版本控制）
    outDir: fileURLToPath(new URL('../static/vue', import.meta.url)),
    emptyOutDir: true,
    target: 'es2018',
    rollupOptions: {
      input: {
        home: fileURLToPath(new URL('./src/entries/home.js', import.meta.url)),
        forum: fileURLToPath(new URL('./src/entries/forum.js', import.meta.url)),
        post_detail: fileURLToPath(new URL('./src/entries/post_detail.js', import.meta.url)),
        auth: fileURLToPath(new URL('./src/entries/auth.js', import.meta.url)),
        users: fileURLToPath(new URL('./src/entries/users.js', import.meta.url)),
        search: fileURLToPath(new URL('./src/entries/search.js', import.meta.url)),
      },
      output: {
        // 文件名确定化：由 ?v= 版本号控制浏览器缓存失效
        entryFileNames: '[name].js',
        chunkFileNames: 'chunks/[name]-[hash].js',
        assetFileNames: 'assets/[name]-[hash][extname]',
      },
    },
  },
})
