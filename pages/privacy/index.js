// 隐私政策（版本 2.1，与 Web 端 /privacy 保持一致）
const theme = require('../../utils/theme.js');

Page({
  data: {
    night: false,
    national: false,
    version: '2.1',
    updated: '2026-08',
  },

  onShow() { theme.sync(this); },
});
