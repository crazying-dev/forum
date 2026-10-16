// 妖精论坛 · 通用工具（与 Web 端 AfterBody.js 的无限纪年 / 时间格式化保持一致）

const CATEGORIES = [
  { key: 'general', label: '综合' },
  { key: 'talk', label: '闲聊' },
  { key: 'question', label: '求助' },
  { key: 'share', label: '分享' },
  { key: 'creative', label: '创作' },
];

const YEAR_KEY = 'forum-year-mode'; // 'wuxian'(默认) | 'ce'

function getYearMode() {
  try { return wx.getStorageSync(YEAR_KEY) === 'ce' ? 'ce' : 'wuxian'; } catch (e) { return 'wuxian'; }
}
function setYearMode(mode) {
  try { wx.setStorageSync(YEAR_KEY, mode === 'ce' ? 'ce' : 'wuxian'); } catch (e) {}
}

// ── 无限纪年法（基准：公历 1604 年 = 无限元年）──
function wuxianYear(ce) {
  ce = parseInt(ce, 10);
  if (isNaN(ce) || ce < 1604) return null;
  return ce - 1603;
}
function wuxianToCE(wy) {
  wy = parseInt(wy, 10);
  if (isNaN(wy) || wy === 0) return '';
  return String(wy > 0 ? wy + 1603 : 1604 + wy);
}
function wuxianYearLabel(ce) {
  ce = parseInt(ce, 10);
  if (isNaN(ce)) return null;
  if (ce >= 1604) {
    const n = ce - 1603;
    return n === 1 ? '无限元年' : '无限' + n + '年';
  }
  return '无限前' + (1604 - ce) + '年';
}
function wuxianYearName(wy) {
  wy = parseInt(wy, 10);
  if (isNaN(wy) || wy === 0) return '';
  return wy > 0 ? (wy === 1 ? '无限元年' : '无限' + wy + '年') : '无限前' + (-wy) + '年';
}
function yearText(ce) {
  ce = parseInt(ce, 10);
  if (isNaN(ce)) return '';
  if (getYearMode() === 'ce') return String(ce);
  const wy = wuxianYear(ce);
  if (wy !== null) return wy === 1 ? '无限元年' : '无限' + wy;
  return '无限前' + (1604 - ce);
}

function pad(n) { return n < 10 ? '0' + n : '' + n; }

// 无时区的 "YYYY-MM-DD HH:MM:SS" 按 UTC 解析（与 Web 端 parseTime 一致）
function parseTime(t) {
  if (!t) return null;
  if (t instanceof Date) return t;
  if (typeof t === 'number') return new Date(t < 1e12 ? t * 1000 : t);
  let s = String(t).trim();
  if (/^\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}(:\d{2})?$/.test(s)) {
    s = s.replace(' ', 'T');
    if (s.length === 16) s += ':00';
    s += 'Z';
  }
  const d = new Date(s);
  return isNaN(d.getTime()) ? null : d;
}

function fmtTime(t) {
  const d = parseTime(t);
  if (!d) return '';
  const diff = (Date.now() - d.getTime()) / 1000;
  if (diff >= 0 && diff < 60) return '刚刚';
  if (diff >= 0 && diff < 3600) return Math.floor(diff / 60) + ' 分钟前';
  if (diff >= 0 && diff < 86400) return Math.floor(diff / 3600) + ' 小时前';
  return yearText(d.getFullYear()) + '-' + pad(d.getMonth() + 1) + '-' + pad(d.getDate()) +
    ' ' + pad(d.getHours()) + ':' + pad(d.getMinutes());
}

function formatDate(t) {
  const d = parseTime(t);
  if (!d) return '';
  return yearText(d.getFullYear()) + '-' + pad(d.getMonth() + 1) + '-' + pad(d.getDate());
}

function categoryLabel(key) {
  for (let i = 0; i < CATEGORIES.length; i++) {
    if (CATEGORIES[i].key === key) return CATEGORIES[i].label;
  }
  return key || '综合';
}

function toast(title, icon) { wx.showToast({ title: title, icon: icon || 'none' }); }

function confirm(content, title) {
  return new Promise((resolve) => {
    wx.showModal({
      title: title || '提示',
      content: content,
      success: (r) => resolve(!!r.confirm),
      fail: () => resolve(false),
    });
  });
}

function loading(title) { wx.showLoading({ title: title || '加载中', mask: true }); }
function hideLoading() { wx.hideLoading(); }

module.exports = {
  CATEGORIES,
  YEAR_KEY,
  getYearMode,
  setYearMode,
  wuxianYear,
  wuxianToCE,
  wuxianYearLabel,
  wuxianYearName,
  yearText,
  parseTime,
  fmtTime,
  formatDate,
  categoryLabel,
  pad,
  toast,
  confirm,
  loading,
  hideLoading,
};
