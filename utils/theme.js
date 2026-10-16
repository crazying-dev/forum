// 妖精论坛 · 主题控制
// 基础偏好：localStorage['forum-theme'] = 'day' | 'night' | ''（缺省）
// 国庆限定：10-01 ~ 10-07 强制生效（假日内不可手动切换），
//   「默认/亮色」渲染为国庆浅色，「暗色」渲染为国庆深色。

const THEME_KEY = 'forum-theme';

function getMode() {
  try {
    const v = wx.getStorageSync(THEME_KEY);
    return (v === 'night' || v === 'day') ? v : '';
  } catch (e) { return ''; }
}
function setMode(mode) {
  try {
    if (mode === 'night' || mode === 'day') wx.setStorageSync(THEME_KEY, mode);
    else wx.removeStorageSync(THEME_KEY);
  } catch (e) {}
}

function isNationalDay(now) {
  now = now || new Date();
  const m = now.getMonth() + 1;
  const d = now.getDate();
  return m === 10 && d >= 1 && d <= 7;
}

function isNight(now) {
  now = now || new Date();
  const mode = getMode();
  if (isNationalDay(now)) return mode === 'night';
  if (mode === 'night') return true;
  if (mode === 'day') return false;
  const h = now.getHours();
  return h >= 18 || h < 6; // 默认：18:00 ~ 06:00 暗色
}

function themeColor(night, national) {
  if (national) return night ? '#3A0D12' : '#C8102E';
  return night ? '#2E4659' : '#6A8C89';
}

function nativeBgColor(night, national) {
  if (national) return night ? '#3A0D12' : '#FBF3E6';
  return night ? '#325a64' : '#D8E6E4';
}

function apply() {
  const now = new Date();
  const national = isNationalDay(now);
  const night = isNight(now);
  const navBg = themeColor(night, national);
  try {
    wx.setNavigationBarColor({ frontColor: '#ffffff', backgroundColor: navBg });
  } catch (e) {}
  try {
    wx.setBackgroundColor({ backgroundColor: nativeBgColor(night, national) });
  } catch (e) {}
  try {
    wx.setTabBarStyle({
      color: night ? '#84A8B9' : '#96A9A7',
      selectedColor: national ? (night ? '#FFD24A' : '#C8102E') : (night ? '#B4D2D8' : '#6A8C89'),
      backgroundColor: night ? '#1A2423' : '#E8EEED',
      borderStyle: night ? 'white' : 'black',
    });
  } catch (e) {}
  if (typeof getApp === 'function') {
    const app = getApp();
    if (app && app.globalData) {
      app.globalData.night = night;
      app.globalData.national = national;
    }
  }
  return { night: night, national: national };
}

// 页面 onShow 调用：应用原生样式并回写页面 data
function sync(page) {
  const s = apply();
  if (page && page.setData) page.setData({ night: s.night, national: s.national });
  return s;
}

// 手动切换（假期限定时忽略）
function toggle() {
  const now = new Date();
  if (isNationalDay(now)) return apply();
  setMode(isNight(now) ? 'day' : 'night');
  return apply();
}

module.exports = {
  THEME_KEY,
  getMode,
  setMode,
  isNationalDay,
  isNight,
  themeColor,
  nativeBgColor,
  apply,
  sync,
  toggle,
};
