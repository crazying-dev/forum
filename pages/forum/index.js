// 论坛：帖子列表 + 分类筛选 + 分页
const api = require('../../utils/api.js');
const util = require('../../utils/util.js');
const theme = require('../../utils/theme.js');

const CATS = [{ key: '', label: '全部' }].concat(util.CATEGORIES);
const PAGE_SIZE = 20;

Page({
  data: {
    night: false,
    national: false,
    cats: CATS,
    cat: '',
    posts: [],
    page: 0,
    hasMore: true,
    loading: false,
    error: '',
  },

  onLoad() {
    this.load(true);
  },

  onShow() {
    theme.sync(this);
  },

  onPullDownRefresh() {
    this.load(true).then(() => wx.stopPullDownRefresh());
  },

  onReachBottom() {
    if (this.data.hasMore && !this.data.loading) this.load(false);
  },

  onCat(e) {
    const cat = e.currentTarget.dataset.key || '';
    if (cat === this.data.cat) return;
    this.setData({ cat: cat, posts: [], page: 0, hasMore: true, error: '' });
    this.load(true);
  },

  load(reset) {
    const self = this;
    if (this.data.loading) return Promise.resolve();
    const page = reset ? 1 : this.data.page + 1;
    this.setData({ loading: true, error: '' });
    const params = { page: page, page_size: PAGE_SIZE };
    if (this.data.cat) params.category = this.data.cat;

    return api.get('/api/posts', params).then((res) => {
      const list = (res && res.posts) || [];
      self.setData({
        posts: reset ? list : self.data.posts.concat(list),
        page: page,
        loading: false,
        hasMore: list.length >= PAGE_SIZE,
      });
    }).catch((err) => {
      self.setData({
        loading: false,
        error: (err && err.message) || '加载失败，请重试',
        hasMore: false,
        posts: reset ? [] : self.data.posts,
      });
    });
  },

  onPostTap(e) {
    wx.navigateTo({ url: '/pages/detail/index?id=' + e.detail.id });
  },

  onCreate() {
    if (!getApp().isLogin()) {
      wx.navigateTo({ url: '/pages/login/index' });
      return;
    }
    wx.navigateTo({ url: '/pages/create/index' });
  },
});
