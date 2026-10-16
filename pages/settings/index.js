// 设置：主题 / 纪年 / 资料编辑 / 修改密码 / 退出
const api = require('../../utils/api.js');
const util = require('../../utils/util.js');
const theme = require('../../utils/theme.js');

const GENDERS = ['保密', '男', '女'];

Page({
  data: {
    night: false,
    national: false,
    isLogin: false,
    themeMode: '',
    yearMode: 'wuxian',
    genders: GENDERS,
    name: '',
    genderIndex: 0,
    age: '',
    intro: '',
    savingProfile: false,
    oldPwd: '',
    newPwd: '',
    changingPwd: false,
  },

  onShow() {
    theme.sync(this);
    const app = getApp();
    const user = app.getUser();
    this.setData({
      isLogin: app.isLogin(),
      themeMode: theme.getMode(),
      yearMode: util.getYearMode(),
      name: (user && user.name) || '',
      genderIndex: (user && typeof user.gender === 'number') ? Math.min(2, Math.max(0, user.gender)) : 0,
      age: (user && user.age) || '',
      intro: (user && user.intro) || '',
    });
    this._loadProfile();
  },

  _loadProfile() {
    const self = this;
    const app = getApp();
    if (!app.isLogin()) return;
    api.get('/api/user/info', {}, { silent: true }).then((res) => {
      if (res && res.success && res.user) {
        const u = res.user;
        app.setUser(u);
        self.setData({
          name: u.name || '',
          genderIndex: typeof u.gender === 'number' ? Math.min(2, Math.max(0, u.gender)) : 0,
          age: u.age || '',
          intro: u.intro || '',
        });
      }
    }).catch(() => {});
  },

  // ── 主题 ────────────────────────────
  onTheme(e) {
    const mode = e.currentTarget.dataset.mode; // auto | day | night
    theme.setMode(mode === 'auto' ? '' : mode);
    theme.sync(this);
    this.setData({ themeMode: theme.getMode() });
  },

  onYear(e) {
    const mode = e.currentTarget.dataset.mode === 'ce' ? 'ce' : 'wuxian';
    util.setYearMode(mode);
    this.setData({ yearMode: mode });
    util.toast(mode === 'ce' ? '已切换为公历纪年' : '已切换为无限纪年');
  },

  // ── 资料 ────────────────────────────
  onName(e) { this.setData({ name: e.detail.value }); },
  onAge(e) { this.setData({ age: e.detail.value }); },
  onIntro(e) { this.setData({ intro: e.detail.value }); },
  onGender(e) { this.setData({ genderIndex: Number(e.detail.value) }); },

  onSaveProfile() {
    const app = getApp();
    if (!app.isLogin()) { util.toast('请先登录'); return; }
    const name = (this.data.name || '').trim();
    if (name.length < 2 || name.length > 20) { util.toast('用户名需 2-20 个字符'); return; }
    if (this.data.savingProfile) return;
    const self = this;
    this.setData({ savingProfile: true });
    api.put('/api/user/info', {
      name: name,
      gender: this.data.genderIndex,
      age: (this.data.age || '').trim(),
      intro: (this.data.intro || '').trim(),
    }).then((res) => {
      self.setData({ savingProfile: false });
      if (res && res.success) {
        if (res.user) app.setUser(res.user);
        util.toast('资料已保存');
      } else {
        util.toast((res && res.message) || '保存失败');
      }
    }).catch((err) => {
      self.setData({ savingProfile: false });
      api.toastError(err);
    });
  },

  // ── 修改密码 ─────────────────────────
  onOldPwd(e) { this.setData({ oldPwd: e.detail.value }); },
  onNewPwd(e) { this.setData({ newPwd: e.detail.value }); },

  onChangePwd() {
    const app = getApp();
    if (!app.isLogin()) { util.toast('请先登录'); return; }
    const oldPwd = this.data.oldPwd || '';
    const newPwd = this.data.newPwd || '';
    if (!oldPwd) { util.toast('请输入原密码'); return; }
    if (newPwd.length < 8 || !/[A-Za-z]/.test(newPwd) || !/\d/.test(newPwd)) {
      util.toast('新密码至少 8 位，且含字母与数字');
      return;
    }
    if (oldPwd === newPwd) { util.toast('新密码不能与原密码相同'); return; }
    if (this.data.changingPwd) return;
    const self = this;
    this.setData({ changingPwd: true });
    api.post('/api/user/password', { old_password: oldPwd, new_password: newPwd })
      .then((res) => {
        self.setData({ changingPwd: false });
        if (res && res.success) {
          app.clearUser();
          util.toast('密码已修改，请重新登录');
          setTimeout(() => wx.redirectTo({ url: '/pages/login/index' }), 800);
        } else {
          util.toast((res && res.message) || '修改失败');
        }
      })
      .catch((err) => {
        self.setData({ changingPwd: false });
        api.toastError(err);
      });
  },

  // ── 退出 ────────────────────────────
  onLogout() {
    const self = this;
    util.confirm('确定要退出登录吗？', '退出登录').then((ok) => {
      if (!ok) return;
      api.post('/api/user/logout', {}).catch(() => {}).then(() => {
        getApp().clearUser();
        self.setData({ isLogin: false });
        util.toast('已退出登录');
        setTimeout(() => wx.navigateBack(), 500);
      });
    });
  },

  onLogin() { wx.navigateTo({ url: '/pages/login/index' }); },
  onPrivacy() { wx.navigateTo({ url: '/pages/privacy/index' }); },
});
