// 发布帖子（需登录）
const api = require('../../utils/api.js');
const util = require('../../utils/util.js');
const theme = require('../../utils/theme.js');

Page({
  data: {
    night: false,
    national: false,
    title: '',
    content: '',
    cats: util.CATEGORIES,
    catIndex: 0,
    submitting: false,
  },

  onLoad() {
    if (!getApp().isLogin()) {
      wx.redirectTo({ url: '/pages/login/index' });
    }
  },

  onShow() {
    theme.sync(this);
  },

  onTitle(e) { this.setData({ title: e.detail.value }); },
  onContent(e) { this.setData({ content: e.detail.value }); },
  onCat(e) { this.setData({ catIndex: Number(e.detail.value) }); },

  onSubmit() {
    if (!getApp().isLogin()) {
      wx.navigateTo({ url: '/pages/login/index' });
      return;
    }
    const title = (this.data.title || '').trim();
    const rawContent = (this.data.content || '').trim();
    if (!title) { util.toast('请输入标题'); return; }
    if (title.length > 100) { util.toast('标题最多 100 字'); return; }
    if (!rawContent) { util.toast('请输入正文内容'); return; }
    if (this.data.submitting) return;

    // 服务端 content 为 HTML，将换行转换为 <br/> 以保留排版
    const content = rawContent.replace(/&/g, '&amp;').replace(/</g, '&lt;')
      .replace(/>/g, '&gt;').replace(/\n/g, '<br/>');
    const category = this.data.cats[this.data.catIndex].key;
    const self = this;

    this.setData({ submitting: true });
    api.post('/api/posts/create', { title: title, content: content, category: category })
      .then((res) => {
        self.setData({ submitting: false });
        if (res && res.success) {
          util.toast('发布成功');
          setTimeout(() => {
            wx.redirectTo({ url: '/pages/detail/index?id=' + res.id });
          }, 600);
        } else {
          util.toast((res && res.message) || '发布失败');
        }
      })
      .catch((err) => {
        self.setData({ submitting: false });
        api.toastError(err);
      });
  },
});
