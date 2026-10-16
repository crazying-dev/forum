// 搜索：帖子 / 用户（type=both）
const api = require('../../utils/api.js');
const util = require('../../utils/util.js');
const theme = require('../../utils/theme.js');

const PAGE_SIZE = 20;

Page({
  data: {
    night: false,
    national: false,
    keyword: '',
    posts: [],
    users: [],
    page: 0,
    hasMore: true,
    loading: false,
    searched: false,
    error: '',
  },

  onLoad(query) {
    if (query && query.k) {
      this.setData({ keyword: query.k });
      this.search(true);
    }
  },

  onShow() { theme.sync(this); },

  onInput(e) { this.setData({ keyword: e.detail.value }); },

  onSearch() {
    const k = (this.data.keyword || '').trim();
    if (k.length < 2) {
      util.toast('关键词至少 2 个字符');
      return;
    }
    this.setData({ posts: [], users: [], page: 0, hasMore: true });
    this.search(true);
  },

  onReachBottom() {
    if (this.data.hasMore && !this.data.loading && this.data.searched) this.search(false);
  },

  search(reset) {
    const self = this;
    const k = (this.data.keyword || '').trim();
    if (k.length < 2) return Promise.resolve();
    if (this.data.loading) return Promise.resolve();
    const page = reset ? 1 : this.data.page + 1;
    this.setData({ loading: true, error: '' });

    return api.get('/api/search', { k: k, page: page, page_size: PAGE_SIZE, type: 'both' })
      .then((res) => {
        const posts = (res && res.posts) || [];
        const users = (res && res.users) || [];
        self.setData({
          posts: reset ? posts : self.data.posts.concat(posts),
          users: reset ? users : self.data.users.concat(users),
          page: page,
          loading: false,
          searched: true,
          hasMore: !!(res && (res.posts_has_more || res.users_has_more)),
        });
      })
      .catch((err) => {
        self.setData({
          loading: false,
          searched: true,
          hasMore: false,
          error: (err && err.message) || '搜索失败，请重试',
        });
      });
  },

  onPostTap(e) {
    wx.navigateTo({ url: '/pages/detail/index?id=' + e.detail.id });
  },

  onUserTap(e) {
    wx.navigateTo({ url: '/pages/user/index?id=' + e.currentTarget.dataset.uid });
  },
});
