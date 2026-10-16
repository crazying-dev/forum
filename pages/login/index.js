// 登录（需人机验证：强制 self-made 滑块）
const api = require('../../utils/api.js');
const util = require('../../utils/util.js');
const theme = require('../../utils/theme.js');

Page({
  data: {
    night: false,
    national: false,
    identifier: '',
    password: '',
    submitting: false,
  },

  onShow() { theme.sync(this); },

  onId(e) { this.setData({ identifier: e.detail.value }); },
  onPwd(e) { this.setData({ password: e.detail.value }); },

  onSubmit() {
    const identifier = (this.data.identifier || '').trim();
    const password = this.data.password || '';
    if (!identifier) { util.toast('请输入用户名或邮箱'); return; }
    if (!password) { util.toast('请输入密码'); return; }
    if (this.data.submitting) return;

    const self = this;
    this.selectComponent('#captcha').capture((token) => {
      if (token === null) return; // 用户取消
      const payload = { password: password };
      if (identifier.indexOf('@') >= 0) payload.email = identifier;
      else payload.name = identifier;
      if (token) payload.captcha_token = token;
      self._doLogin(payload);
    });
  },

  _doLogin(payload) {
    const self = this;
    this.setData({ submitting: true });
    api.post('/api/user/login', payload).then((res) => {
      self.setData({ submitting: false });
      if (res && res.success) {
        getApp().setUser(res.user);
        util.toast('登录成功');
        setTimeout(() => self._back(), 500);
      } else {
        util.toast((res && res.message) || '登录失败');
      }
    }).catch((err) => {
      self.setData({ submitting: false });
      util.toast((err && err.message) || '登录失败');
    });
  },

  _back() {
    const pages = getCurrentPages();
    if (pages.length > 1) wx.navigateBack();
    else wx.switchTab({ url: '/pages/index/index' });
  },

  onRegister() { wx.redirectTo({ url: '/pages/register/index' }); },
  onForgot() {
    wx.setClipboardData({ data: 'https://www.yjlt.top/reset-password' });
    util.toast('已复制网页版找回地址');
  },
});
