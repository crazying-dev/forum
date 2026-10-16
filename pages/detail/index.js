// 帖子详情：正文 / 点赞 / 收藏 / 评论（两级楼中楼）/ 删除 / 举报
const api = require('../../utils/api.js');
const util = require('../../utils/util.js');
const theme = require('../../utils/theme.js');

Page({
  data: {
    night: false,
    national: false,
    id: '',
    post: null,
    comments: [],
    liked: false,
    favorited: false,
    loading: true,
    error: '',
    isLogin: false,
    myId: '',
    isAuthor: false,
    commentInput: '',
    replyTo: null,
    submitting: false,
  },

  onLoad(query) {
    this.setData({ id: (query && query.id) || '' });
    this.load();
  },

  onShow() {
    theme.sync(this);
    const app = getApp();
    const u = app.getUser() || {};
    this.setData({ isLogin: app.isLogin(), myId: u.id || '' });
    this._syncAuthor();
  },

  onPullDownRefresh() {
    this.load().then(() => wx.stopPullDownRefresh());
  },

  _syncAuthor() {
    const p = this.data.post;
    this.setData({ isAuthor: !!(p && this.data.myId && p.user_id === this.data.myId) });
  },

  load() {
    const self = this;
    if (!this.data.id) {
      this.setData({ loading: false, error: '缺少帖子参数' });
      return Promise.resolve();
    }
    this.setData({ loading: true, error: '' });
    return api.get('/api/posts/' + this.data.id).then((res) => {
      const post = res && res.post;
      if (!post) {
        self.setData({ loading: false, error: '帖子不存在' });
        return;
      }
      post.timeText = util.fmtTime(post.created_at);
      post.catLabel = util.categoryLabel(post.category);
      self.setData({
        post: post,
        comments: self._buildTree((res && res.comments) || []),
        liked: !!res.liked,
        favorited: !!res.favorited,
        loading: false,
      });
      self._syncAuthor();
      wx.setNavigationBarTitle({ title: post.title || '帖子详情' });
    }).catch((err) => {
      self.setData({ loading: false, error: (err && err.message) || '加载失败，请重试' });
    });
  },

  _cmp(a, b) {
    const ta = util.parseTime(a.created_at);
    const tb = util.parseTime(b.created_at);
    return (ta ? ta.getTime() : 0) - (tb ? tb.getTime() : 0);
  },

  _buildTree(list) {
    const byId = {};
    list.forEach((c) => { byId[c.id] = c; });
    const tops = [];
    const childMap = {};
    list.forEach((c) => {
      const item = Object.assign({}, c, { timeText: util.fmtTime(c.created_at), replies: [] });
      const pid = c.parent_id;
      if (!pid || !byId[pid]) {
        tops.push(item);
        return;
      }
      let root = byId[pid];
      let guard = 0;
      while (root && root.parent_id && byId[root.parent_id] && guard < 30) {
        root = byId[root.parent_id];
        guard++;
      }
      item.reply_to_name = byId[pid] ? byId[pid].user_name : '';
      const rid = root ? root.id : pid;
      if (!childMap[rid]) childMap[rid] = [];
      childMap[rid].push(item);
    });
    tops.sort(this._cmp);
    tops.forEach((t) => { t.replies = (childMap[t.id] || []).sort(this._cmp); });
    return tops;
  },

  // ── 交互 ────────────────────────────
  _requireLogin() {
    if (!getApp().isLogin()) {
      wx.navigateTo({ url: '/pages/login/index' });
      return false;
    }
    return true;
  },

  onLike() {
    if (!this._requireLogin()) return;
    const self = this;
    api.post('/api/posts/' + this.data.id + '/like', {}).then((res) => {
      if (res && res.success) self.setData({ liked: !!res.liked, 'post.likes': res.likes });
    }).catch(api.toastError);
  },

  onFavorite() {
    if (!this._requireLogin()) return;
    const self = this;
    api.post('/api/posts/' + this.data.id + '/favorite', {}).then((res) => {
      if (res && res.success) {
        self.setData({ favorited: !!res.favorited });
        util.toast(res.favorited ? '已收藏' : '已取消收藏');
      }
    }).catch(api.toastError);
  },

  onReport() {
    if (!this._requireLogin()) return;
    const self = this;
    const reasons = ['垃圾广告', '色情低俗', '人身攻击', '违法违规', '其他'];
    wx.showActionSheet({
      itemList: reasons,
      success(r) {
        api.post('/api/posts/' + self.data.id + '/report', { reason: reasons[r.tapIndex] })
          .then(() => util.toast('举报已提交'))
          .catch(api.toastError);
      },
    });
  },

  onDeletePost() {
    const self = this;
    util.confirm('确定删除这篇帖子吗？删除后不可恢复。').then((ok) => {
      if (!ok) return;
      api.post('/api/posts/' + self.data.id + '/delete', {}).then(() => {
        util.toast('已删除');
        setTimeout(() => wx.navigateBack(), 600);
      }).catch(api.toastError);
    });
  },

  onTapUser(e) {
    const uid = e.currentTarget.dataset.uid;
    if (!uid) return;
    if (uid === this.data.myId) {
      wx.navigateTo({ url: '/pages/user/index?id=' + uid });
      return;
    }
    wx.navigateTo({ url: '/pages/user/index?id=' + uid });
  },

  // ── 评论 ──────────────────────────
  onCommentInput(e) {
    this.setData({ commentInput: e.detail.value });
  },

  onReply(e) {
    const ds = e.currentTarget.dataset;
    this.setData({ replyTo: { id: ds.cid, name: ds.cname || '用户' } });
  },

  onCancelReply() {
    this.setData({ replyTo: null });
  },

  onSubmitComment() {
    if (!this._requireLogin()) return;
    const content = (this.data.commentInput || '').trim();
    if (!content) {
      util.toast('请输入评论内容');
      return;
    }
    if (this.data.submitting) return;
    const self = this;
    const payload = { content: content };
    if (this.data.replyTo) payload.parent_id = this.data.replyTo.id;
    this.setData({ submitting: true });
    api.post('/api/posts/' + this.data.id + '/comments/create', payload).then(() => {
      self.setData({ submitting: false, commentInput: '', replyTo: null });
      return self.reloadComments();
    }).catch((err) => {
      self.setData({ submitting: false });
      api.toastError(err);
    });
  },

  reloadComments() {
    const self = this;
    return api.get('/api/posts/' + this.data.id + '/comments', { page: 1, page_size: 50 }, { silent: true })
      .then((res) => {
        self.setData({ comments: self._buildTree((res && res.comments) || []) });
      }).catch(() => {});
  },

  onLikeComment(e) {
    if (!this._requireLogin()) return;
    const cid = e.currentTarget.dataset.cid;
    const self = this;
    api.post('/api/comments/' + cid + '/like', {}).then(() => self.reloadComments()).catch(api.toastError);
  },

  onDeleteComment(e) {
    const cid = e.currentTarget.dataset.cid;
    const self = this;
    util.confirm('确定删除这条评论吗？').then((ok) => {
      if (!ok) return;
      api.post('/api/comments/' + cid + '/delete', {}).then(() => {
        util.toast('已删除');
        self.reloadComments();
      }).catch(api.toastError);
    });
  },
});
