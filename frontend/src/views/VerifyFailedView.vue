<template>
  <div class="verify-container">
    <div class="verify-card failed">
      <div class="verify-icon"><i class="fa fa-times-circle"></i></div>
      <h2>验证失败</h2>
      <p>验证链接已过期或无效，请重新操作。</p>
      <button class="verify-btn" @click="location.href = '/login'">返回登录</button>
    </div>
  </div>
</template>
