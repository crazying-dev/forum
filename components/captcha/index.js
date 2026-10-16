// 自研滑块验证码组件（对接 /api/captcha/*，强制 provider=slider）
// 用法：
//   const cap = this.selectComponent('#captcha');
//   cap.capture(function (token) {
//     // token === null  -> 用户取消
//     // token === ''    -> 服务端已关闭验证，无需携带 captcha_token
//     // token === 'xxx' -> 已通过验证，业务请求携带 captcha_token: 'xxx'
//   });
const api = require('../../utils/api.js');

Component({
  data: {
    visible: false,
    loading: false,
    ready: false,
    busy: false,
    error: false,
    tip: '',
    bg: '',
    piece: '',
    stageW: 0,
    stageH: 0,
    pieceW: 0,
    pieceTop: 0,
    pieceLeft: 0,
    maxLeft: 0,
  },

  methods: {
    capture(cb) {
      this._cb = typeof cb === 'function' ? cb : function () {};
      this._token = '';
      this._scale = 1;
      this._startX = 0;
      this._startLeft = 0;
      this.setData({
        visible: true,
        loading: true,
        ready: false,
        busy: false,
        error: false,
        tip: '正在加载验证…',
        pieceLeft: 0,
      });
      this._fetch();
    },

    noop() {},

    _close(token) {
      this.setData({ visible: false, ready: false, busy: false });
      const cb = this._cb;
      this._cb = null;
      if (cb) cb(token);
    },

    onCancel() {
      this._close(null);
    },

    _fetch() {
      const self = this;
      api.post('/api/captcha/challenge?provider=slider', {}).then((res) => {
        if (!res || !res.success) {
          self.setData({ loading: false, tip: (res && res.message) || '加载失败，请重试' });
          return;
        }
        // 服务端已关闭人机验证
        if (res.enabled === false || !res.token) {
          self._close('');
          return;
        }
        if (res.provider !== 'slider') {
          self.setData({ loading: false, tip: '当前环境不支持该验证方式' });
          return;
        }
        let winW = 375;
        try {
          const info = wx.getWindowInfo ? wx.getWindowInfo() : wx.getSystemInfoSync();
          winW = (info && info.windowWidth) || 375;
        } catch (e) {}
        const maxStageW = Math.max(200, winW - 64);
        const natural = res.width || 320;
        const scale = Math.min(1, maxStageW / natural);
        const stageW = natural * scale;
        const pieceW = (res.piece_size || 50) * scale;
        self._token = res.token;
        self._scale = scale;
        self.setData({
          loading: false,
          ready: true,
          bg: res.bg,
          piece: res.piece,
          stageW: stageW,
          stageH: (res.height || 180) * scale,
          pieceW: pieceW,
          pieceTop: (res.y || 0) * scale,
          pieceLeft: 0,
          maxLeft: Math.max(0, stageW - pieceW),
          tip: '拖动拼图块，填补缺口',
        });
      }).catch((err) => {
        self.setData({ loading: false, tip: (err && err.message) || '加载失败，请重试' });
      });
    },

    onTouchStart(e) {
      if (!this.data.ready || this.data.busy) return;
      const t = e.touches && e.touches[0];
      if (!t) return;
      this._startX = t.clientX;
      this._startLeft = this.data.pieceLeft;
    },

    onTouchMove(e) {
      if (!this.data.ready || this.data.busy) return;
      const t = e.touches && e.touches[0];
      if (!t) return;
      let left = this._startLeft + (t.clientX - this._startX);
      if (left < 0) left = 0;
      if (left > this.data.maxLeft) left = this.data.maxLeft;
      this.setData({ pieceLeft: left });
    },

    onTouchEnd() {
      if (!this.data.ready || this.data.busy) return;
      const x = Math.round(this.data.pieceLeft / this._scale);
      const self = this;
      this.setData({ busy: true, tip: '正在校验…' });
      api.post('/api/captcha/verify', { captcha_token: this._token, captcha_x: x })
        .then((res) => {
          if (res && res.success && res.token) {
            self.setData({ busy: false });
            self._close(res.token);
            return;
          }
          self._fail((res && res.message) || '验证失败，请重试');
        })
        .catch((err) => {
          const msg = (err && err.data && err.data.message) || (err && err.message) || '验证失败，请重试';
          self._fail(msg);
        });
    },

    _fail(msg) {
      const self = this;
      this.setData({ busy: false, error: true, tip: msg });
      // 失败后服务端已作废 token，必须重新拉取挑战
      setTimeout(() => {
        self.setData({
          error: false,
          pieceLeft: 0,
          bg: '',
          piece: '',
          ready: false,
          loading: true,
          tip: '正在重新加载…',
        });
        self._fetch();
      }, 700);
    },
  },
});
