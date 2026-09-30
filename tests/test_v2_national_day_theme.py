"""国庆节主题（国庆浅色 / 国庆深色）契约测试。

规则：
  · 在现有「亮色 / 暗色 / 默认」基础上新增两套国庆调色板；
  · 两套国庆主题**不支持手动切换**（设置下拉中不可见，仍只有 day/night/default 三项）；
  · 国庆假期（10-01 00:00 ~ 10-07 24:00，本地时间）强制生效：
      显式「亮色」或「默认」→ 国庆浅色；显式「暗色」→ 国庆深色；
      假期内「默认」不跟随时间，恒为国庆浅色；
  · `localStorage['forum-theme']` 仍只记录「基础偏好」，假期结束自动还原。

均为静态源码断言（无需启动服务、无数据库依赖）。
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import config  # noqa: E402

AFTERBODY = ROOT / "static" / "js" / "AfterBody.js"
CSS = ROOT / "static" / "css" / "main.css"
BASE = ROOT / "templates" / "base.html"

# 与 :root / .night-mode 对齐的全部设计令牌（--world-width 仅在 :root 定义，不计入）
TOKENS = [
    "--color-text-primary",
    "--color-text-secondary",
    "--color-text-tertiary",
    "--color-text-light",
    "--color-text-accent",
    "--color-bg-body",
    "--color-bg-header",
    "--color-bg-card",
    "--color-bg-input",
    "--color-bg-hover",
    "--color-bg-footer",
    "--color-border",
    "--color-border-focus",
    "--color-primary",
    "--color-primary-hover",
    "--color-shadow",
    "--color-bg-secondary",
    "--color-bg-icon",
    "--color-bg-icon-hover",
    "--color-bg-item-hover",
    "--color-bg-item-active",
    "--color-border-divider",
    "--color-text-muted",
]


def _read(p: Path) -> str:
    return p.read_text(encoding="utf-8")


def _block(css: str, selector: str) -> str:
    m = re.search(re.escape(selector) + r"\s*\{([^}]*)\}", css)
    assert m, f"CSS 缺少规则块 {selector}"
    return m.group(1)


# ── 1. CSS：两套国庆调色板存在且令牌齐全 ──
def test_css_defines_national_day_palettes():
    css = _read(CSS)
    light = _block(css, ".national-day")
    dark = _block(css, ".night-mode.national-day")
    for token in TOKENS:
        assert re.search(rf"{re.escape(token)}\s*:", light), f"国庆浅色未定义 {token}"
        assert re.search(rf"{re.escape(token)}\s*:", dark), f"国庆深色未定义 {token}"
    # 配色方向：浅色=中国红主色 + 米白底；深色=亮金主色 + 暗红底
    assert "--color-primary: #C8102E" in light, "国庆浅色主色不是中国红 #C8102E"
    assert "--color-bg-body: #FBF3E6" in light, "国庆浅色底不是暖白/米底"
    assert "--color-primary: #FFD24A" in dark, "国庆深色主色不是亮金 #FFD24A"
    assert "--color-bg-body: #3A0D12" in dark, "国庆深色底不是暗红"


# ── 2. CSS：必须在 .night-mode 之后声明，保证叠加优先级正确 ──
def test_css_national_day_declared_after_night_mode():
    css = _read(CSS)
    i_night = css.find(".night-mode {")
    i_light = css.find(".national-day {")
    i_dark = css.find(".night-mode.national-day {")
    assert i_night != -1 and i_light != -1 and i_dark != -1, "国庆主题类未声明"
    assert i_night < i_light < i_dark, \
        "国庆主题类必须在 .night-mode 之后、且深色在后（否则叠加优先级/具体度失效）"
    # 深色必须是复合选择器（具体度 0,2,0），否则会被浅色块覆盖
    assert re.search(r"\.night-mode\.national-day\s*\{", css), \
        "国庆深色未使用 .night-mode.national-day 复合选择器"


# ── 3. base.html：首屏内联脚本先于首帧应用国庆类 ──
def test_base_inline_script_applies_national_day_before_paint():
    base = _read(BASE)
    assert "isNationalDay" in base, "base.html 内联脚本缺少 isNationalDay 判定"
    assert "classList.add('national-day')" in base, "内联脚本未在首帧应用 national-day"
    # 国庆窗口：10 月 1 日 ~ 7 日
    assert re.search(r"NAT_MONTH\s*=\s*10", base) and "NAT_FROM = 1" in base and "NAT_TO = 7" in base, \
        "内联脚本国庆窗口不是 10-01 ~ 10-07"
    # 假期内仅显式暗色才用深色（默认/亮色 → 浅色）
    assert re.search(r"night\s*=\s*\(t === 'night'\)", base), \
        "内联脚本未实现「假期内仅显式暗色走深色」"
    # 地址栏/PWA 主题色跟随
    assert "meta[name=\"theme-color\"]" in base, "内联脚本未同步 theme-color"
    assert "'#C8102E'" in base and "'#3A0D12'" in base, "theme-color 缺少国庆配色"


# ── 4. AfterBody.js：applyTheme 承载假期强制映射并对外暴露 ──
def test_afterbody_apply_theme_holiday_rules():
    js = _read(AFTERBODY)
    assert "function applyTheme(pref)" in js, "AfterBody.js 缺少 applyTheme(pref)"
    assert "function isNationalDay(d)" in js, "AfterBody.js 缺少 isNationalDay(d)"
    body = js[js.find("function applyTheme"):]
    body = body[: body.find("\n  }\n") + 5]
    # 假期内：仅 pref === 'night' 走深色
    assert re.search(r"if\s*\(nat\)\s*\{\s*night\s*=\s*\(pref === 'night'\)", body), \
        "applyTheme 假期分支未固定为「仅显式暗色走深色」"
    assert "classList.toggle('national-day', nat)" in body, "applyTheme 未切换 national-day"
    assert "classList.toggle('night-mode', night)" in body, "applyTheme 未切换 night-mode"
    # 手动切换仅记录基础偏好，渲染层由 applyTheme 决定
    assert "applyTheme: applyTheme," in js, "__yoyoApp 未暴露 applyTheme"
    assert re.search(r"function setTheme\(v\)", js), "setTheme 不存在"
    st = js[js.find("function setTheme(v)"):]
    st = st[: st.find("\n  }\n") + 5]
    assert "applyTheme(pref)" in st, "setTheme 未调用 applyTheme（假期覆盖会失效）"
    assert "localStorage.setItem('forum-theme', v)" not in st, \
        "setTheme 不应把国庆值写入 localStorage（应只存基础偏好）"


# ── 5. 国庆主题不可手动切换：设置下拉仍只有 亮/暗/默认 三项 ──
def test_settings_dropdown_still_only_three_themes():
    base = _read(BASE)
    themes = re.findall(r'data-theme="([^"]*)"', base)
    assert themes == ["day", "night", "default"], \
        f"设置下拉主题项被改动（应仍为 day/night/default）：{themes}"
    assert 'data-theme="national' not in base, "国庆主题出现在设置下拉中（应不可手动切换）"
    assert "国庆" not in base.split("<div class=\"side-setting-dropdown\"")[1], \
        "设置下拉中出现了国庆主题文案（应不可见）"


# ── 6. 静态版本号已提升（CSS/JS 变更后用户不应拿到缓存旧文件）──
def test_static_version_bumped_for_national_day():
    assert int(config.STATIC_VERSION) >= 31, \
        "新增国庆主题后 STATIC_VERSION 应提升到 >= 31"


if __name__ == "__main__":
    test_css_defines_national_day_palettes()
    test_css_national_day_declared_after_night_mode()
    test_base_inline_script_applies_national_day_before_paint()
    test_afterbody_apply_theme_holiday_rules()
    test_settings_dropdown_still_only_three_themes()
    test_static_version_bumped_for_national_day()
    print("ALL_PASSED")
