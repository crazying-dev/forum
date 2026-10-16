// 注册（需邮箱验证码 + 人机验证；两步各消耗一次滑块）
const api = require('../../utils/api.js');
const util = require('../../utils/util.js');
const theme = require('../../utils/theme.js');

const EMAIL_RE = /^[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}$/;

Page({
  data: {
    night: false,
    national: false,
    name: '',
    email: '',
    code: '',
    password: '',
    submitting: false,
    sending: false,
    countdown: 0,
  },

  onShow() { theme.sync(this); },
  onUnload() { this._stopCountdown(); },

  onName(e) { this.setData({ name: e.detail.value }); },
  onEmail(e) { this.setData({ email: e.detail.value }); },
  onCode(e) { this.setData({ code: e.detail.value }); },
  onPwd(e) { this.setData({ password: e.detail.value }); },

  _stopCountdown() {
    if (this._timer) { clearInterval(this._timer); this._timer = null; }
  },

  _startCountdown() {
    const self = this;
    this._stopCountdown();
    this.setData({ countdown: 60 });
    this._timer = setInterval(() => {
      const n = self.data.countdown - 1;
      if (n <= 0) { self._stopCountdown(); self.setData({ countdown: 0 }); }
      else self.setData({ countdown: n });
    }, 1000);
  },

  onSendCode() {
    if (this.data.countdown > 0 || this.data.sending) return;
    const email = (this.data.email || '').trim();
    if (!EMAIL_RE.test(email)) { util.toast('请输入有效的邮箱'); return; }
    const self = this;
    this.selectComponent('#captcha').capture((token) => {
      if (token === null) return;
      const payload = { email: email };
      if (token) payload.captcha_token = token;
      self.setData({ sending: true });
      api.post('/api/email/send-register-code', payload).then((res) => {
        self.setData({ sending: false });
        if (res && res.success) {
          util.toast('验证码已发送');
          self._startCountdown();
        } else {
          util.toast((res && res.message) || '发送失败');
        }
      }).catch((err) => {
        self.setData({ sending: false });
        util.toast((err && err.message) || '发送失败');
      });
    });
  },

  onSubmit() {
    const name = (this.data.name || '').trim();
    const email = (this.data.email || '').trim();
    const code = (this.data.code || '').trim();
    const password = this.data.password || '';
    if (name.length < 2 || name.length > 20) { util.toast('用户名需 2-20 个字符'); return; }
    if (!EMAIL_RE.test(email)) { util.toast('请输入有效的邮箱'); return; }
    if (!/^\d{6}$/.test(code)) { util.toast('请输入 6 位数字验证码'); return; }
    if (password.length < 8 || !/[A-Za-z]/.test(password) || !/\d/.test(password)) {
      util.toast('密码至少 8 位，且含字母与数字');
      return;
    }
    if (this.data.submitting) return;

    const self = this;
    this.selectComponent('#captcha').capture((token) => {
      if (token === null) return;
      const payload = { name: name, email: email, password: password, code: code };
      if (token) payload.captcha_token = token;
      self.setData({ submitting: true });
      api.post('/api/user/register', payload).then((res) => {
        self.setData({ submitting: false });
        if (res && res.success) {
          if (res.user) getApp().setUser(res.user);
          util.toast('注册成功');
          setTimeout(() => {
            const pages = getCurrentPages();
            if (pages.length > 1) wx.navigateBack();
            else wx.switchTab({ url: '/pages/index/index' });
          }, 600);
        } else {
          util.toast((res && res.message) || '注册失败');
        }
      }).catch((err) => {
        self.setData({ submitting: false });
        util.toast((err && err.message) || '注册失败');
      });
    });
  },

  onLogin() { wx.redirectTo({ url: '/pages/login/index' }); },
});
