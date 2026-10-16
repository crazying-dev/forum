// 首页：推荐（随机）/ 最新 / 热门 / 收藏
const api = require('../../utils/api.js');
const theme = require('../../utils/theme.js');

const TABS = [
  { key: 'random', label: '推荐' },
  { key: 'time', label: '最新' },
  { key: 'comprehensive', label: '热门' },
  { key: 'favorites', label: '收藏' },
];
const PAGE_SIZE = 20;

Page({
  data: {
    night: false,
    national: false,
    tabs: TABS,
    kind: 'random',
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
    // 从登录页返回后，收藏 tab 可能需要重新加载
    if (this.data.kind === 'favorites' && this._needReloadFav) {
      this._needReloadFav = false;
      this.load(true);
    }
  },

  onPullDownRefresh() {
    this.load(true).then(() => wx.stopPullDownRefresh());
  },

  onReachBottom() {
    if (this.data.hasMore && !this.data.loading) this.load(false);
  },

  onTab(e) {
    const kind = e.currentTarget.dataset.kind;
    if (kind === this.data.kind) return;
    this.setData({ kind: kind, posts: [], page: 0, hasMore: true, error: '' });
    this.load(true);
  },

  load(reset) {
    const self = this;
    const kind = this.data.kind;

    if (kind === 'favorites' && !getApp().isLogin()) {
      this._needReloadFav = true;
      this.setData({ posts: [], page: 0, hasMore: false, loading: false, error: '登录后可查看收藏' });
      return Promise.resolve();
    }
    if (this.data.loading) return Promise.resolve();

    const page = reset ? 1 : this.data.page + 1;
    this.setData({ loading: true, error: '' });

    let task;
    if (kind === 'random') {
      task = api.get('/api/posts/random', { limit: 200 });
    } else if (kind === 'favorites') {
      const uid = getApp().getUser().id;
      task = api.get('/api/user/' + uid + '/favorites', { page: page, page_size: PAGE_SIZE });
    } else {
      task = api.get('/api/posts', { sort: kind, page: page, page_size: PAGE_SIZE });
    }

    return task.then((res) => {
      const list = (res && res.posts) || [];
      const posts = reset ? list : self.data.posts.concat(list);
      self.setData({
        posts: posts,
        page: page,
        loading: false,
        hasMore: kind === 'random' ? false : list.length >= PAGE_SIZE,
      });
    }).catch((err) => {
      const msg = (err && err.message) || '加载失败，请重试';
      self.setData({
        loading: false,
        error: msg,
        hasMore: false,
        posts: reset ? [] : self.data.posts,
      });
    });
  },

  onPostTap(e) {
    wx.navigateTo({ url: '/pages/detail/index?id=' + e.detail.id });
  },

  onSearch() {
    wx.navigateTo({ url: '/pages/search/index' });
  },

  onCreate() {
    if (!getApp().isLogin()) {
      wx.navigateTo({ url: '/pages/login/index' });
      return;
    }
    wx.navigateTo({ url: '/pages/create/index' });
  },

  onGoLogin() {
    wx.navigateTo({ url: '/pages/login/index' });
  },
});
