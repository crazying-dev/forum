// 用户主页：资料 + 关注 + 帖子 / 收藏
const api = require('../../utils/api.js');
const util = require('../../utils/util.js');
const theme = require('../../utils/theme.js');

const PAGE_SIZE = 20;

Page({
  data: {
    night: false,
    national: false,
    id: '',
    user: null,
    isSelf: false,
    isFollowing: false,
    tab: 'posts',
    posts: [],
    page: 0,
    hasMore: true,
    loading: false,
    error: '',
  },

  onLoad(query) {
    const tab = (query && query.tab === 'fav') ? 'fav' : 'posts';
    this.setData({ id: (query && query.id) || '', tab: tab });
    this.loadUser();
    this.loadList(true);
  },

  onShow() { theme.sync(this); },

  onPullDownRefresh() {
    const self = this;
    this.loadUser().then(() => self.loadList(true)).then(() => wx.stopPullDownRefresh());
  },

  onReachBottom() {
    if (this.data.hasMore && !this.data.loading) this.loadList(false);
  },

  loadUser() {
    const self = this;
    if (!this.data.id) return Promise.resolve();
    return api.get('/api/user/' + this.data.id).then((res) => {
      if (res && res.success && res.user) {
        self.setData({
          user: res.user,
          isSelf: !!res.user.is_self,
          isFollowing: !!res.user.is_following,
        });
        wx.setNavigationBarTitle({ title: res.user.name || '用户主页' });
      }
    }).catch((err) => {
      self.setData({ error: (err && err.message) || '加载失败' });
    });
  },

  loadList(reset) {
    const self = this;
    if (!this.data.id) return Promise.resolve();
    if (this.data.tab === 'fav' && !this.data.isSelf) {
      this.setData({ posts: [], hasMore: false });
      return Promise.resolve();
    }
    if (this.data.loading) return Promise.resolve();
    const page = reset ? 1 : this.data.page + 1;
    this.setData({ loading: true });
    const url = this.data.tab === 'fav'
      ? '/api/user/' + this.data.id + '/favorites'
      : '/api/user/' + this.data.id + '/posts';
    return api.get(url, { page: page, page_size: PAGE_SIZE }, { silent: true }).then((res) => {
      const list = (res && res.posts) || [];
      self.setData({
        posts: reset ? list : self.data.posts.concat(list),
        page: page,
        loading: false,
        hasMore: list.length >= PAGE_SIZE,
      });
    }).catch((err) => {
      self.setData({ loading: false, hasMore: false });
      if (err && err.status !== 401) api.toastError(err);
    });
  },

  onSwitchTab(e) {
    const tab = e.currentTarget.dataset.tab;
    if (tab === this.data.tab) return;
    this.setData({ tab: tab, posts: [], page: 0, hasMore: true });
    this.loadList(true);
  },

  onFollow() {
    if (!getApp().isLogin()) {
      wx.navigateTo({ url: '/pages/login/index' });
      return;
    }
    const self = this;
    api.post('/api/user/' + this.data.id + '/follow', {}).then((res) => {
      if (res && res.success) {
        const following = !!res.following;
        const user = Object.assign({}, self.data.user);
        if (user.stats && user.stats.follower_count !== undefined) {
          user.stats.follower_count = Math.max(0, user.stats.follower_count + (following ? 1 : -1));
        }
        self.setData({ isFollowing: following, user: user });
        util.toast(following ? '已关注' : '已取消关注');
      }
    }).catch(api.toastError);
  },

  onPostTap(e) {
    wx.navigateTo({ url: '/pages/detail/index?id=' + e.detail.id });
  },

  onFollowers() {
    wx.showToast({ title: '列表功能可在网页端查看', icon: 'none' });
  },
});
