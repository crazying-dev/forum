<template>
  <div class="wiki-page">
    <div class="wiki-header">
      <h2>罗小黑战记 Wiki</h2>
    </div>
    <div class="wiki-container">
      <a href="/WIKI/GuanFang" class="wiki-card">
        <div class="wiki-card-image">
          <img :src="'/static/img/wiki/guanfang_cover.webp'" alt="官方内容" class="WIKIWithBackground">
        </div>
        <div class="wiki-card-content">
          <h3>官方</h3>
          <p>官方发布的内容信息</p>
          <span class="wiki-card-link">查看详情 &rarr;</span>
        </div>
      </a>
      <a href="/WIKI/Personal" class="wiki-card">
        <div class="wiki-card-image">
          <img :src="'/static/img/wiki/personal_cover.jpg'" alt="个人内容" class="WIKIWithBackground">
        </div>
        <div class="wiki-card-content">
          <h3>个人</h3>
          <p>用户分享的个人创作</p>
          <span class="wiki-card-link">查看详情 &rarr;</span>
        </div>
      </a>
    </div>
    <div class="wiki-footer">
      <p>更多内容持续更新中...</p>
    </div>
  </div>
</template>
