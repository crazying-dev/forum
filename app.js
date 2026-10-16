// 妖精论坛 · 微信小程序入口
// 对接 https://www.yjlt.top 现有 API（Cookie 鉴权：token + ID）
const api = require('./utils/api.js');
const theme = require('./utils/theme.js');

const USER_KEY = 'forum-user';

App({
  globalData: {
    user: null,
    night: false,
    national: false,
    version: api.APP_VERSION,
    systemInfo: null,
  },

  onLaunch() {
    // 系统信息（旧基础库用 getSystemInfoSync 兜底）
    try {
      this.globalData.systemInfo = wx.getWindowInfo
        ? wx.getWindowInfo()
        : wx.getSystemInfoSync();
    } catch (e) {
      this.globalData.systemInfo = {};
    }

    // 主题（亮/暗/国庆限定）
    const t = theme.apply();
    this.globalData.night = t.night;
    this.globalData.national = t.national;

    // 恢复本地缓存的用户资料；能否真正登录仍以服务端 Cookie 为准
    try {
      const cached = wx.getStorageSync(USER_KEY);
      if (cached && cached.id) {
        this.globalData.user = cached;
      }
    } catch (e) {}
  },

  // ── 用户态 ───────────────────────────────
  setUser(user) {
    this.globalData.user = user || null;
    try {
      if (user && user.id) {
        wx.setStorageSync(USER_KEY, user);
      } else {
        wx.removeStorageSync(USER_KEY);
      }
    } catch (e) {}
  },

  clearUser() {
    this.setUser(null);
  },

  getUser() {
    return this.globalData.user;
  },

  isLogin() {
    const u = this.globalData.user;
    return !!(u && u.id);
  },

  // 拉取当前登录用户；失败（401）则清空本地态
  refreshUser() {
    const self = this;
    return api.get('/api/user/info', {}, { silent: true }).then((res) => {
      if (res && res.success && res.user) {
        self.setUser(res.user);
        return res.user;
      }
      self.clearUser();
      return null;
    }).catch(() => {
      self.clearUser();
      return null;
    });
  },
});
