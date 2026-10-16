// 世界频道：HTTP 轮询（3s）+ 发送消息
// 服务端 GET /api/world/ALL 返回裸数组（时间倒序）；客户端反转为聊天顺序并保留最近 200 条
const api = require('../../utils/api.js');
const util = require('../../utils/util.js');
const theme = require('../../utils/theme.js');

const POLL_MS = 3000;
const MAX_KEEP = 200;

Page({
  data: {
    night: false,
    national: false,
    messages: [],
    input: '',
    sending: false,
    scrollInto: '',
    loaded: false,
    isLogin: false,
  },

  onLoad() {
    this._atBottom = true;
    this._forceBottom = true;
    this.refresh();
    this.startPoll();
  },

  onReady() {
    const self = this;
    wx.createSelectorQuery().select('.msg-scroll').boundingClientRect((rect) => {
      if (rect) self._viewH = rect.height;
    }).exec();
  },

  onShow() {
    theme.sync(this);
    this.setData({ isLogin: getApp().isLogin() });
    this.refresh();
    this.startPoll();
  },

  onHide() { this.stopPoll(); },
  onUnload() { this.stopPoll(); },

  startPoll() {
    if (this._timer) return;
    const self = this;
    this._timer = setInterval(() => self.refresh(), POLL_MS);
  },

  stopPoll() {
    if (this._timer) {
      clearInterval(this._timer);
      this._timer = null;
    }
  },

  refresh() {
    const self = this;
    return api.get('/api/world/ALL', {}, { silent: true }).then((list) => {
      const force = self._forceBottom;
      self._forceBottom = false;
      self._apply(list, force);
    }).catch(() => {});
  },

  _apply(list, force) {
    const arr = (list || []).slice().reverse();
    const cut = arr.slice(Math.max(0, arr.length - MAX_KEEP));
    const messages = cut.map((m) => Object.assign({}, m, { timeText: util.fmtTime(m.created_at) }));
    const patch = { messages: messages, loaded: true };
    if (force || this._atBottom) {
      const last = messages[messages.length - 1];
      patch.scrollInto = last ? ('msg-' + last.id) : '';
      this._atBottom = true;
    }
    this.setData(patch);
  },

  onScroll(e) {
    const d = e.detail || {};
    if (typeof d.scrollHeight === 'number' && this._viewH) {
      this._atBottom = (d.scrollHeight - d.scrollTop - this._viewH) < 32;
    }
  },

  onInput(e) {
    this.setData({ input: e.detail.value });
  },

  onSend() {
    if (!getApp().isLogin()) {
      wx.navigateTo({ url: '/pages/login/index' });
      return;
    }
    const content = (this.data.input || '').trim();
    if (!content) {
      util.toast('请输入内容');
      return;
    }
    if (this.data.sending) return;
    const self = this;
    this.setData({ sending: true });
    api.post('/api/world/Send', { content: content }).then(() => {
      self.setData({ input: '', sending: false });
      self._forceBottom = true;
      self._atBottom = true;
      self.refresh();
    }).catch((err) => {
      self.setData({ sending: false });
      api.toastError(err);
    });
  },

  onTapAvatar(e) {
    const uid = e.currentTarget.dataset.uid;
    if (uid) wx.navigateTo({ url: '/pages/user/index?id=' + uid });
  },
});
