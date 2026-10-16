// 帖子列表卡片（首页 / 论坛 / 搜索 / 用户主页 复用）
const util = require('../../utils/util.js');

Component({
  properties: {
    post: { type: Object, value: {} },
    showCategory: { type: Boolean, value: true },
  },
  data: {
    timeText: '',
    catLabel: '',
  },
  observers: {
    post(p) {
      if (!p) return;
      this.setData({
        timeText: util.fmtTime(p.created_at),
        catLabel: util.categoryLabel(p.category),
      });
    },
  },
  methods: {
    onTap() {
      const p = this.data.post || {};
      if (!p.id) return;
      this.triggerEvent('tap', { id: p.id });
    },
  },
});
