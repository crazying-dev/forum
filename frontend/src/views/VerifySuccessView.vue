<script setup>
// 读取 user_id cookie，跳转个人主页
function goProfile() {
  const m = document.cookie.match(/(?:^|;\s*)user_id=([^;]+)/)
  location.href = '/users/' + (m ? m[1] : '')
}
</script>

<template>
  <div class="verify-container">
    <div class="verify-card success">
      <div class="verify-icon"><i class="fa fa-check-circle"></i></div>
      <h2>验证成功</h2>
      <p>您的邮箱已成功验证，感谢您的使用！</p>
      <button class="verify-btn" @click="goProfile">返回个人主页</button>
    </div>
  </div>
</template>
