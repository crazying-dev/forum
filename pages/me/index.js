// 我的：登录态 / 个人资料 / 入口
const api = require('../../utils/api.js');
const util = require('../../utils/util.js');
const theme = require('../../utils/theme.js');

Page({
  data: {
    night: false,
    national: false,
    isLogin: false,
    user: null,
    stats: null,
    loading: false,
  },

  onShow() {
    theme.sync(this);
    this.loadUser();
  },

  onPullDownRefresh() {
    this.loadUser().then(() => wx.stopPullDownRefresh());
  },

  loadUser() {
    const self = this;
    const app = getApp();
    if (!app.isLogin()) {
      this.setData({ isLogin: false, user: null, stats: null });
      return Promise.resolve();
    }
    this.setData({ loading: true });
    return api.get('/api/user/info', {}, { silent: true }).then((res) => {
      if (res && res.success && res.user) {
        app.setUser(res.user);
        self.setData({
          isLogin: true,
          user: res.user,
          stats: res.user.stats || null,
          loading: false,
        });
      } else {
        app.clearUser();
        self.setData({ isLogin: false, user: null, stats: null, loading: false });
      }
    }).catch(() => {
      self.setData({ loading: false });
    });
  },

  onLogin() {
    wx.navigateTo({ url: '/pages/login/index' });
  },

  onRegister() {
    wx.navigateTo({ url: '/pages/register/index' });
  },

  onMyPage() {
    const u = this.data.user;
    if (u) wx.navigateTo({ url: '/pages/user/index?id=' + u.id });
  },

  onFavorites() {
    const u = this.data.user;
    if (u) wx.navigateTo({ url: '/pages/user/index?id=' + u.id + '&tab=fav' });
  },

  onPublish() {
    wx.navigateTo({ url: '/pages/create/index' });
  },

  onSearch() {
    wx.navigateTo({ url: '/pages/search/index' });
  },

  onSettings() {
    wx.navigateTo({ url: '/pages/settings/index' });
  },

  onPrivacy() {
    wx.navigateTo({ url: '/pages/privacy/index' });
  },

  onLogout() {
    const self = this;
    util.confirm('确定要退出登录吗？', '退出登录').then((ok) => {
      if (!ok) return;
      api.post('/api/user/logout', {}).catch(() => {}).then(() => {
        getApp().clearUser();
        self.setData({ isLogin: false, user: null, stats: null });
        util.toast('已退出登录');
      });
    });
  },
});
