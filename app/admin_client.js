/**
 * 妖精论坛管理员客户端内核（初版）
 *
 * 功能:
 *     1. 查看被举报的帖子列表
 *     2. 修改用户信息
 *     3. 删除帖子
 *     4. 删除评论
 *     5. 封禁/解封用户
 *     6. 查看所有用户
 *     7. 查看帖子详情
 *     8. 数据缓存与事件通知
 *
 * 浏览器用法:
 *     const kernel = new AdminKernel({
 *       apiUrl: 'https://your-api.vercel.app',
 *       adminId: 'YJXXXXXXXXXX',
 *       adminToken: 'xxxxxxxxxx'
 *     });
 *     await kernel.connect();
 *     const reports = await kernel.listReports();
 *
 * Node.js 用法:
 *     const AdminKernel = require('./admin_client.js');
 *     const kernel = new AdminKernel({ ... });
 *
 * 事件:
 *     kernel.on('connect', () => console.log('已连接'));
 *     kernel.on('error', (err) => console.error(err));
 *     kernel.on('cache:clear', () => {});
 */

(function (global, factory) {
  if (typeof module === 'object' && typeof module.exports === 'object') {
    module.exports = factory();
  } else {
    global.AdminKernel = factory();
  }
})(typeof window !== 'undefined' ? window : this, function () {
  'use strict';

  // ========================
  // 工具函数
  // ========================

  async function _sha256(text) {
    if (typeof globalThis.crypto !== 'undefined' && globalThis.crypto.subtle) {
      const encoder = new TextEncoder();
      const data = encoder.encode(text);
      const hashBuffer = await globalThis.crypto.subtle.digest('SHA-256', data);
      const hashArray = Array.from(new Uint8Array(hashBuffer));
      return hashArray.map(b => b.toString(16).padStart(2, '0')).join('');
    }
    const nodeCrypto = require('crypto');
    return nodeCrypto.createHash('sha256').update(text, 'utf8').digest('hex');
  }

  function _getTimePassword() {
    const now = new Date();
    const year = now.getFullYear();
    const month = String(now.getMonth() + 1).padStart(2, '0');
    const day = String(now.getDate()).padStart(2, '0');
    const hour = String(now.getHours()).padStart(2, '0');
    return `${year}-${month}-${day}-${hour}`;
  }

  class SimpleEventEmitter {
    constructor() {
      this._events = {};
    }

    on(event, handler) {
      if (!this._events[event]) {
        this._events[event] = [];
      }
      this._events[event].push(handler);
      return () => this.off(event, handler);
    }

    off(event, handler) {
      if (!this._events[event]) return;
      this._events[event] = this._events[event].filter(h => h !== handler);
    }

    emit(event, ...args) {
      if (!this._events[event]) return;
      for (const handler of this._events[event]) {
        try {
          handler(...args);
        } catch (e) {
          console.error(`[AdminKernel] 事件 ${event} 处理错误:`, e);
        }
      }
    }
  }

  class TTLCache {
    constructor(ttl = 60000) {
      this._ttl = ttl;
      this._data = new Map();
    }

    set(key, value) {
      this._data.set(key, { value, expires: Date.now() + this._ttl });
    }

    get(key) {
      const entry = this._data.get(key);
      if (!entry) return undefined;
      if (Date.now() > entry.expires) {
        this._data.delete(key);
        return undefined;
      }
      return entry.value;
    }

    invalidate(pattern) {
      if (!pattern) {
        this._data.clear();
        return;
      }
      for (const key of this._data.keys()) {
        if (key.includes(pattern)) {
          this._data.delete(key);
        }
      }
    }

    clear() {
      this._data.clear();
    }
  }

  // ========================
  // 管理员内核
  // ========================

  class AdminKernel extends SimpleEventEmitter {
    constructor(options = {}) {
      super();
      this.apiUrl = options.apiUrl || '';
      if (this.apiUrl && !/^https?:\/\//i.test(this.apiUrl)) {
        this.apiUrl = 'https://' + this.apiUrl;
      }
      this.adminId = options.adminId || '';
      this.adminToken = options.adminToken || '';
      this.timeout = options.timeout || 15000;
      this.retryCount = options.retryCount || 0;
      this.retryDelay = options.retryDelay || 1000;

      this.connected = false;
      this._cache = new TTLCache(options.cacheTTL || 60000);
    }

    async _generateTimeToken(sendTime) {
      const raw = `${this.adminId}${sendTime}`;
      const hash = await _sha256(raw);
      return hash.substring(0, 16);
    }

    async _request(action, args = {}) {
      if (!this.adminId || !this.adminToken) {
        const err = new Error('请先配置管理员ID和令牌');
        this.emit('error', err);
        throw err;
      }
      if (!this.apiUrl) {
        const err = new Error('请先配置 API 地址');
        this.emit('error', err);
        throw err;
      }

      const sendTime = Date.now() / 1000;
      const timeToken = await this._generateTimeToken(sendTime.toString());
      const password = _getTimePassword();

      const payload = {
        password: password,
        AdminID: this.adminId,
        AdminToken: this.adminToken,
        TimeToken: timeToken,
        SendTime: sendTime.toString(),
        RunMessage: JSON.stringify({ action, args })
      };

      let lastError;
      for (let attempt = 0; attempt <= this.retryCount; attempt++) {
        try {
          const result = await this._doFetch(payload);
          return result;
        } catch (e) {
          lastError = e;
          if (attempt < this.retryCount) {
            this.emit('retry', { action, attempt: attempt + 1, error: e });
            await new Promise(r => setTimeout(r, this.retryDelay * (attempt + 1)));
          }
        }
      }

      this.emit('error', lastError);
      throw lastError;
    }

    async _doFetch(payload) {
      let response;
      let rawBody;

      if (typeof globalThis.fetch !== 'undefined') {
        response = await fetch(this.apiUrl, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload),
          signal: typeof AbortSignal !== 'undefined' && AbortSignal.timeout ? AbortSignal.timeout(this.timeout) : undefined
        });
        rawBody = await response.text();
      } else {
        const https = require('https');
        const http = require('http');
        const urlMod = require('url');
        const parsed = urlMod.parse(this.apiUrl);
        const lib = parsed.protocol === 'https:' ? https : http;

        rawBody = await new Promise((resolve, reject) => {
          const req = lib.request({
            hostname: parsed.hostname,
            port: parsed.port,
            path: parsed.path || '/',
            method: 'POST',
            headers: {
              'Content-Type': 'application/json',
              'Content-Length': Buffer.byteLength(JSON.stringify(payload))
            },
            timeout: this.timeout
          }, (res) => {
            response = {
              ok: res.statusCode >= 200 && res.statusCode < 300,
              status: res.statusCode
            };
            let body = '';
            res.on('data', d => body += d);
            res.on('end', () => resolve(body));
          });
          req.on('error', reject);
          req.on('timeout', () => {
            req.destroy();
            reject(new Error('请求超时'));
          });
          req.write(JSON.stringify(payload));
          req.end();
        });
      }

      let result;
      try {
        result = JSON.parse(rawBody);
      } catch (e) {
        const snippet = rawBody.substring(0, 200).replace(/\s+/g, ' ');
        const status = response ? response.status : 'unknown';
        throw new Error(`服务器返回非 JSON 数据 (HTTP ${status}): ${snippet}`);
      }

      if (!result.success) {
        throw new Error(result.message || '请求失败');
      }
      return result.data;
    }

    _cacheKey(action, args) {
      return `${action}:${JSON.stringify(args)}`;
    }

    async _cachedRequest(action, args = {}) {
      const key = this._cacheKey(action, args);
      const cached = this._cache.get(key);
      if (cached !== undefined) {
        this.emit('cache:hit', { action, key });
        return cached;
      }
      const data = await this._request(action, args);
      this._cache.set(key, data);
      this.emit('cache:miss', { action, key });
      return data;
    }

    clearCache(pattern) {
      this._cache.invalidate(pattern);
      this.emit('cache:clear', { pattern });
    }

    async connect() {
      try {
        await this.getStats();
        this.connected = true;
        this.emit('connect');
        return true;
      } catch (e) {
        this.connected = false;
        throw e;
      }
    }

    // ========================
    // 举报管理
    // ========================

    async listReports(status = null) {
      return this._cachedRequest('list_reports', { status });
    }

    async resolveReport(reportId) {
      const result = await this._request('resolve_report', { report_id: reportId });
      this.clearCache('list_reports');
      this.clearCache('get_stats');
      return result;
    }

    // ========================
    // 用户管理
    // ========================

    async listUsers() {
      return this._cachedRequest('list_users');
    }

    async findUser(key, value) {
      return this._cachedRequest('find_user', { key, value });
    }

    async findUserSmart(identifier) {
      return this._cachedRequest('find_user_smart', { identifier });
    }

    async updateUser(userId, key, value) {
      const result = await this._request('update_user', { user_id: userId, key, value });
      this.clearCache('list_users');
      this.clearCache('find_user');
      this.clearCache('find_user_smart');
      this.clearCache('get_stats');
      return result;
    }

    async banUser(userId) {
      const result = await this._request('ban_user', { user_id: userId });
      this.clearCache('list_users');
      this.clearCache('find_user');
      this.clearCache('find_user_smart');
      this.clearCache('get_stats');
      return result;
    }

    async unbanUser(userId) {
      const result = await this._request('unban_user', { user_id: userId });
      this.clearCache('list_users');
      this.clearCache('find_user');
      this.clearCache('find_user_smart');
      this.clearCache('get_stats');
      return result;
    }

    // ========================
    // 帖子管理
    // ========================

    async getPostDetail(postId) {
      return this._cachedRequest('get_post_detail', { post_id: postId });
    }

    async deletePost(postId) {
      const result = await this._request('delete_post', { post_id: postId });
      this.clearCache('get_post_detail');
      this.clearCache('list_reports');
      this.clearCache('get_stats');
      return result;
    }

    async getPostComments(postId) {
      return this._cachedRequest('get_post_comments', { post_id: postId });
    }

    async deleteComment(commentId) {
      const result = await this._request('delete_comment', { comment_id: commentId });
      this.clearCache('get_post_comments');
      this.clearCache('get_stats');
      return result;
    }

    // ========================
    // 统计信息
    // ========================

    async getStats() {
      return this._cachedRequest('get_stats');
    }

    // ========================
    // 批量操作
    // ========================

    async banUsers(userIds) {
      const results = [];
      for (const id of userIds) {
        try {
          const ok = await this.banUser(id);
          results.push({ id, success: true, ok });
        } catch (e) {
          results.push({ id, success: false, error: e.message });
        }
      }
      return results;
    }

    async resolveReports(reportIds) {
      const results = [];
      for (const id of reportIds) {
        try {
          const ok = await this.resolveReport(id);
          results.push({ id, success: true, ok });
        } catch (e) {
          results.push({ id, success: false, error: e.message });
        }
      }
      return results;
    }

    async deletePosts(postIds) {
      const results = [];
      for (const id of postIds) {
        try {
          const ok = await this.deletePost(id);
          results.push({ id, success: true, ok });
        } catch (e) {
          results.push({ id, success: false, error: e.message });
        }
      }
      return results;
    }

    // ========================
    // 配置持久化（浏览器）
    // ========================

    saveConfig() {
      if (typeof localStorage === 'undefined') return false;
      try {
        localStorage.setItem('admin_kernel_config', JSON.stringify({
          apiUrl: this.apiUrl,
          adminId: this.adminId,
          adminToken: this.adminToken
        }));
        return true;
      } catch (e) {
        return false;
      }
    }

    loadConfig() {
      if (typeof localStorage === 'undefined') return false;
      try {
        const raw = localStorage.getItem('admin_kernel_config');
        if (!raw) return false;
        const config = JSON.parse(raw);
        this.apiUrl = config.apiUrl || this.apiUrl;
        if (this.apiUrl && !/^https?:\/\//i.test(this.apiUrl)) {
          this.apiUrl = 'https://' + this.apiUrl;
        }
        this.adminId = config.adminId || this.adminId;
        this.adminToken = config.adminToken || this.adminToken;
        return true;
      } catch (e) {
        return false;
      }
    }

    clearConfig() {
      if (typeof localStorage === 'undefined') return false;
      try {
        localStorage.removeItem('admin_kernel_config');
        return true;
      } catch (e) {
        return false;
      }
    }
  }

  return AdminKernel;
});
