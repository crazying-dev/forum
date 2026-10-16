// 妖精论坛 · 网络请求封装
// 服务端约定：Cookie 鉴权（token + ID，HttpOnly），请求/响应均 JSON。
// 小程序的 wx.request 会对同一域名自动维持 Cookie 会话，因此登录态无需手动传递。

const BASE_URL = 'https://www.yjlt.top';
const APP_VERSION = '1.0.0';
// 服务端版本门禁只识别 windows/android/web；未知平台（wechat）会 fail-open 放行，
// 避免小程序被 426 拦截（小程序无法就地升级，需走审核发布）。
const CLIENT_PLATFORM = 'wechat';

function buildQuery(params) {
  if (!params) return '';
  const parts = [];
  Object.keys(params).forEach((k) => {
    const v = params[k];
    if (v === undefined || v === null || v === '') return;
    parts.push(encodeURIComponent(k) + '=' + encodeURIComponent(v));
  });
  return parts.length ? ('?' + parts.join('&')) : '';
}

function clientHeaders(extra) {
  const h = {
    'X-Client-Platform': CLIENT_PLATFORM,
    'X-Client-Version': APP_VERSION,
  };
  if (extra) {
    Object.keys(extra).forEach((k) => { if (extra[k] !== undefined) h[k] = extra[k]; });
  }
  return h;
}

function makeError(status, body) {
  const message = (body && (body.message || body.error)) || ('请求失败（' + status + '）');
  return {
    status: status,
    code: (body && (body.code || body.error)) || '',
    message: message,
    data: body || null,
  };
}

function handleVersionTooLow(body) {
  const msg = (body && body.message) || '版本过低，请更新后再使用';
  wx.showModal({ title: '需要更新', content: msg, showCancel: false });
}

function request(method, path, data, opts) {
  opts = opts || {};
  const url = /^https?:\/\//.test(path) ? path : (BASE_URL + path);
  const body = (method === 'GET') ? null : (data === undefined ? {} : data);
  return new Promise((resolve, reject) => {
    wx.request({
      url: url,
      method: method,
      data: body,
      header: clientHeaders(Object.assign(
        { 'Content-Type': 'application/json; charset=utf-8' },
        opts.header || {}
      )),
      timeout: opts.timeout || 15000,
      success(res) {
        const status = res.statusCode;
        const payload = res.data;
        if (status === 426) {
          handleVersionTooLow(payload);
          reject(makeError(status, payload));
          return;
        }
        if (status >= 200 && status < 300) {
          resolve(payload);
          return;
        }
        if (status === 401) {
          // 登录态失效：清理本地用户
          try {
            const app = getApp();
            if (app && app.clearUser) app.clearUser();
          } catch (e) {}
        }
        reject(makeError(status, payload));
      },
      fail(err) {
        reject({ status: 0, code: 'NETWORK_ERROR', message: '网络异常，请检查网络后重试', raw: err });
      },
    });
  });
}

function get(path, params, opts) {
  return request('GET', path + buildQuery(params), null, opts);
}
function post(path, data, opts) { return request('POST', path, data, opts); }
function put(path, data, opts) { return request('PUT', path, data, opts); }

// 上传文件（如头像 multipart/form-data）
function upload(path, filePath, name, formData, opts) {
  opts = opts || {};
  const url = /^https?:\/\//.test(path) ? path : (BASE_URL + path);
  return new Promise((resolve, reject) => {
    wx.uploadFile({
      url: url,
      filePath: filePath,
      name: name || 'file',
      formData: formData || {},
      header: clientHeaders(opts.header),
      timeout: opts.timeout || 60000,
      success(res) {
        let payload = res.data;
        if (typeof payload === 'string') {
          try { payload = JSON.parse(payload); } catch (e) {}
        }
        if (res.statusCode >= 200 && res.statusCode < 300) resolve(payload);
        else reject(makeError(res.statusCode, payload));
      },
      fail(err) {
        reject({ status: 0, code: 'NETWORK_ERROR', message: '上传失败，请重试', raw: err });
      },
    });
  });
}

// 统一的错误提示（不展示“请先登录”，交由页面自行引导）
function toastError(err) {
  const msg = (err && err.message) || '操作失败';
  wx.showToast({ title: msg, icon: 'none' });
}

module.exports = {
  BASE_URL,
  APP_VERSION,
  CLIENT_PLATFORM,
  buildQuery,
  request,
  get,
  post,
  put,
  upload,
  makeError,
  toastError,
};
