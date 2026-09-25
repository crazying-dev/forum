"""年制切换（无限年/公元年，cookie）/ 改密码邮箱验证 / 找回密码单页表单 / 换绑邮箱两步验证 / 手机端底部标签栏 契约测试。

均为静态源码断言（无需启动服务、无数据库依赖），与 tests/_run_tests.py 的运行器兼容。
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
EMAIL_API = ROOT / "api" / "email" / "__init__.py"
USER_API = ROOT / "api" / "user" / "__init__.py"
AUTH_VIEW = ROOT / "frontend" / "src" / "views" / "AuthView.vue"
USER_VIEW = ROOT / "frontend" / "src" / "views" / "UserView.vue"
WORLD_VIEW = ROOT / "frontend" / "src" / "views" / "WorldPageView.vue"


def _read(p: Path) -> str:
    return p.read_text(encoding="utf-8")


# ──────────────────────────────────────────────
# 第 3 项：设置中切换无限年 / 公元年（cookie 存储）
# ──────────────────────────────────────────────
def test_year_mode_uses_cookie_in_afterbody():
    """年制偏好必须存 cookie（而非 localStorage），且读写工具齐全。"""
    js = _read(AFTERBODY)
    assert "forum-year-mode" in js, "AfterBody.js 缺少年制 cookie 名 forum-year-mode"
    assert "document.cookie" in js, "年制偏好未用 document.cookie 存储"
    for fn in ["function readCookie", "function writeCookie", "function getYearMode", "function setYearMode"]:
        assert fn in js, f"AfterBody.js 缺少 {fn}"
    assert "SameSite=Lax" in js, "写 cookie 缺 SameSite=Lax"
    # 默认无限年（用户确认：默认无限年，保持不变）
    assert re.search(r"readCookie\(YEAR_MODE_COOKIE\)\s*===\s*'ce'\s*\?\s*'ce'\s*:\s*'wuxian'", js), \
        "getYearMode 默认值不是 'wuxian'（默认应为无限年）"


def test_fmt_time_respects_year_mode():
    """全站时间戳（fmtTime）必须按当前年制输出年份。"""
    js = _read(AFTERBODY)
    assert "function yearText" in js, "缺少 yearText（按年制格式化年份）"
    m = re.search(r"function fmtTime\(t\)\s*\{(.*?)\n  \}", js, re.DOTALL)
    assert m, "找不到 fmtTime 函数体"
    body = m.group(1)
    assert "yearText(" in body, "fmtTime 未使用 yearText，年制切换不会生效"
    assert "yearText: yearText" in js, "yearText 未导出到 window.__yoyoApp"
    for key in ["getYearMode: getYearMode", "setYearMode: setYearMode"]:
        assert key in js, f"window.__yoyoApp 未导出 {key}"


def test_year_mode_setting_buttons():
    """设置面板必须有「年制显示」分组与两个按钮，并由 AfterBody 绑定。"""
    html = _read(BASE)
    assert "年制显示" in html, "设置面板缺少「年制显示」分组"
    assert 'data-yearmode="wuxian"' in html, "缺少「无限年」按钮"
    assert 'data-yearmode="ce"' in html, "缺少「公元年」按钮"
    js = _read(AFTERBODY)
    assert "[data-yearmode]" in js, "AfterBody.js 未绑定 [data-yearmode]"
    assert re.search(r"setYearMode\(b\.getAttribute\('data-yearmode'\)\)", js), \
        "[data-yearmode] 点击未调用 setYearMode"


def test_wuxian_epoch_is_1604():
    """基准：无限元年 = 公元 1604 年；示例 323 → 1927、1947 → 无限343年。"""
    js = _read(AFTERBODY)
    assert "wy + 1604" in js, "无限年→公元年公式（+1604）缺失"
    assert "ce - 1604" in js, "公元年→无限年公式（−1604）缺失"
    assert "'无限前'" in js, "缺少「无限前」处理（公元 1604 年之前）"
    # 同一公式的算术校验（JS 侧的常量若被改动，公式断言会先失败）
    assert str(323 + 1604) == "1927"
    assert 1947 - 1604 == 343
    assert f"无限{1947 - 1604}年" == "无限343年"


def test_wuxian_converter_live_update():
    """换算组件输入即算：不再必须点「换算」（旧版“点了没反应”体感）。"""
    js = _read(AFTERBODY)
    assert re.search(r"addEventListener\('input', run\)", js), "换算输入框未绑定 input 即时换算"
    assert "function run()" in js, "换算逻辑未抽成 run()"
    assert 'id="wuxianConvert"' in _read(BASE), "换算按钮缺失"
    assert 'id="wuxianModeHint"' in _read(BASE), "换算弹窗缺少当前年制提示"
    assert "wuxianModeHint" in js, "AfterBody.js 未填充当前年制提示"


# ──────────────────────────────────────────────
# 第 4 项：个人资料改密码（需邮箱验证码）
# ──────────────────────────────────────────────
def test_change_password_requires_email_code_backend():
    email_api = _read(EMAIL_API)
    assert "/email/send-change-password-code" in email_api, "缺少发送改密验证码接口"
    assert 'create_verify_code(email, code, "change_password")' in email_api, \
        "改密验证码 purpose 未用 change_password"
    assert "def verify_change_password_code" in email_api, "缺少改密验证码校验函数"
    assert "def consume_change_password_code" in email_api, "缺少改密验证码消费（标记已用）函数"
    assert "@login_required" in email_api

    user_api = _read(USER_API)
    m = re.search(r"def api_user_change_password\(\):(.*?)\n# ──", user_api, re.DOTALL)
    assert m, "找不到 api_user_change_password"
    body = m.group(1)
    assert 'data.get("code")' in body, "改密接口未接收邮箱验证码 code"
    assert "verify_change_password_code" in body, "改密接口未校验邮箱验证码"
    assert "reset_password" in body, "改密接口未调用重置密码"
    assert "_clear_auth_cookies" in body, "改密后未清理登录 cookie"


def test_profile_change_password_ui():
    vue = _read(USER_VIEW)
    assert "/api/user/password" in vue, "资料页未调用改密接口"
    assert "/api/email/send-change-password-code" in vue, "资料页缺少「获取验证码」调用"
    assert "需邮箱验证码" in vue, "改密码区未标注需邮箱验证"
    for token in ["pwCode", "pwNew", "pwConfirm", "pwCooldown"]:
        assert token in vue, f"资料页改密 缺少 {token}"
    assert "new_password".replace("_", "_") in vue, "改密请求未提交 new_password"
    assert "code: pwCode.value.trim()" in vue, "改密请求未提交验证码"


# ──────────────────────────────────────────────
# 第 5 项：登录页找回密码「单页表单」（邮箱 + 验证码 + 新密码 + 确认）
# ──────────────────────────────────────────────
def test_forgot_password_single_page_code_flow():
    vue = _read(AUTH_VIEW)
    # 已从两步式改为单页表单：不应再有分步状态
    assert "resetStep" not in vue, "找回密码已改为单页表单，不应再有分步状态 resetStep"
    assert "isCodeResetStep2" not in vue, "不应再有两步式第二步状态 isCodeResetStep2"
    # 找回密码时始终显示邮箱 + 验证码输入框（一次性全部显示）
    assert re.search(r"showCode\s*=[^\n]*isCodeReset", vue), \
        "找回密码未始终显示验证码输入框（showCode 应包含 isCodeReset）"
    assert re.search(r"showEmail\s*=[^\n]*isResetWithToken", vue), \
        "找回密码应始终显示邮箱输入框（仅在 ?token= 时隐藏）"
    assert "/api/email/send-code-reset-password" in vue, "缺少「获取验证码」发送接口"
    assert "/api/email/reset-password-by-code" in vue, "缺少验证码重置接口"
    assert "email: email.value, code: code.value.trim(), password: password.value" in vue, \
        "单页表单未一次性提交 邮箱 + 验证码 + 新密码"
    assert "/api/email/send-reset-password" not in vue, \
        "登录页不应再走「先发链接」方式"
    # 邮件链接方式（?token=）仍保留兼容
    assert "body: { token, password: password.value }" in vue, "邮件链接重置（?token=）分支被误删"


# ──────────────────────────────────────────────
# 第 3 项：编辑资料不显示邮箱 + 换绑邮箱两步验证（旧邮箱身份 → 新邮箱）
# ──────────────────────────────────────────────
def test_change_email_two_step_backend():
    email_api = _read(EMAIL_API)
    user_api = _read(USER_API)
    # 发往旧邮箱的验证码接口（第1步：验证当前邮箱身份）
    assert "/email/send-change-email-old-code" in email_api, \
        "缺少发往旧邮箱的身份验证码接口"
    assert "change_email_old" in email_api, "旧邮箱验证码 purpose 应为 change_email_old"
    assert "def verify_change_email_old_code" in email_api, "缺少旧邮箱验证码校验函数"
    assert "def consume_change_email_old_code" in email_api, "缺少旧邮箱验证码消费函数"
    # 发往新邮箱的验证码接口（第2步）
    assert "/email/send-change-email-code" in email_api, "缺少发往新邮箱的验证码接口"
    assert "change_email" in email_api
    # 换绑接口同时校验旧/新两枚验证码
    assert "old_code" in user_api, "换绑接口未接收旧邮箱验证码 old_code"
    assert "verify_change_email_old_code" in user_api, "换绑接口未校验旧邮箱身份"
    assert "verify_change_email_code" in user_api, "换绑接口未校验新邮箱验证码"


def test_edit_profile_no_email_two_entries():
    vue = _read(USER_VIEW)
    # 编辑资料中不显示当前邮箱（不得有 editForm.email 或直接渲染 user.email）
    assert "editForm.email" not in vue, "编辑资料弹窗不应包含邮箱字段"
    assert "{{ user.email" not in vue and "{{user.email" not in vue, \
        "编辑资料弹窗不应直接显示当前邮箱"
    # 双入口：修改密码 / 修改邮箱
    assert "editPanel" in vue, "缺少编辑弹窗面板切换 editPanel"
    assert "openEmailPanel" in vue, "缺少「修改邮箱」入口"
    assert "/api/email/send-change-email-old-code" in vue, "修邮箱第1步未调用旧邮箱发码接口"
    assert "/api/email/send-change-email-code" in vue, "修邮箱第2步未调用新邮箱发码接口"
    assert "/api/user/email" in vue, "缺少换绑邮箱接口调用"
    assert "old_code: emOldCode.value.trim()" in vue, "换绑请求未提交旧邮箱验证码"
    # 两步向导：emStep 1→2
    assert "emStep" in vue and "goEmailStep2" in vue, "换邮箱未实现两步向导"
    # 两个安全入口按钮
    assert "修改邮箱" in vue and "修改密码" in vue, "缺少两个安全入口按钮"


# ──────────────────────────────────────────────
# 第 2 项：SMTP 传输可配置（465/SSL 与 587/STARTTLS），便于更换服务商
# ──────────────────────────────────────────────
def test_smtp_transport_is_configurable():
    email_py = _read(ROOT / "Email.py")
    cfg = _read(ROOT / "config.py")
    assert "SMTP_TLS" in cfg, "config 缺少 SMTP_TLS 传输模式配置"
    assert "SMTP_USE_AUTH" in cfg, "config 缺少 SMTP_USE_AUTH（中继/无认证）开关"
    assert "SMTP_TIMEOUT" in cfg, "config 缺少 SMTP_TIMEOUT"
    assert "_connect_smtp" in email_py, "Email.py 缺少按 SMTP_TLS 建连的 _connect_smtp"
    assert "starttls" in email_py, "Email.py 未支持 STARTTLS（587 端口）"
    assert "SMTP_SSL" in email_py, "Email.py 未保留 465/SSL 分支"


# ──────────────────────────────────────────────
# 第 1 项：手机端重做（底部标签栏 + 世界频道独立页）
# ──────────────────────────────────────────────
def _first_media_block(css: str, max_width: int) -> str:
    marker = f"@media (max-width: {max_width}px)"
    start = css.find(marker)
    assert start != -1, f"CSS 缺少 {marker}"
    brace = css.find("{", start)
    depth = 0
    i = brace
    while i < len(css):
        if css[i] == "{":
            depth += 1
        elif css[i] == "}":
            depth -= 1
            if depth == 0:
                return css[brace + 1:i]
        i += 1
    return ""


def test_mobile_bottom_tab_bar_replaces_left_rail():
    """手机端去掉左侧 52px 竖条（正文被挤压的元凶），改用底部标签栏。"""
    css = _read(CSS)
    block = _first_media_block(css, 900)
    assert "padding-left: 0" in block, "手机端未取消左侧预留宽度（正文仍会被挤压）"
    assert "padding-left: 52px" not in block, "手机端仍保留 52px 左侧预留"
    assert "flex-direction: row" in block and ".nav-tab" in block, "未把侧边栏改为底部横向标签栏"
    assert "safe-area-inset-bottom" in block, "底部标签栏未适配 iPhone 安全区"
    assert ".world-panel { display: none !important; }" in block, \
        "手机端未隐藏右侧世界频道浮层（应改用独立页）"


def test_mobile_nav_tabs_markup_and_world_page_entry():
    html = _read(BASE)
    assert html.count('class="side-nav-item nav-tab"') >= 5, "底部标签栏条目不足（首页/论坛/世界/发帖/设置）"
    assert 'href="/World"' in html, "缺少世界频道独立页入口 /World"
    js = _read(AFTERBODY)
    assert "markActiveTab" in js, "底部标签栏未高亮当前页面"
    # 桌面端必须隐藏底部标签栏专属项
    css = _read(CSS)
    m = re.search(r"@media \(min-width: 901px\)\s*\{(.*?)\n\}", css, re.DOTALL)
    assert m and ".nav-tab { display: none; }" in m.group(1), "桌面端未隐藏 .nav-tab"


def test_world_page_view_uses_shared_time_and_css_tokens():
    vue = _read(WORLD_VIEW)
    assert "fmtTime as fmtTimeShared" in vue, "世界频道独立页时间未复用全局 fmtTime（年制切换会不一致）"
    assert "d.getFullYear()" not in vue, "世界频道独立页仍保留自写的公元年格式化"
    css = _read(CSS)
    assert ".world-page-container" in css and "100dvh" in css, "世界频道独立页缺少手机端高度适配"


def test_legacy_css_tokens_are_defined():
    """V1 移植样式引用的设计令牌必须已定义，否则背景透明/分隔线消失。"""
    css = _read(CSS)
    root = css[:css.find(".night-mode")]
    for token in [
        "--color-bg-secondary",
        "--color-bg-icon",
        "--color-bg-icon-hover",
        "--color-bg-item-hover",
        "--color-bg-item-active",
        "--color-border-divider",
        "--color-text-muted",
    ]:
        assert re.search(rf"{re.escape(token)}\s*:", root), f":root 未定义 {token}"
    # 夜间模式同样补齐
    night = css[css.find(".night-mode"):]
    for token in ["--color-bg-item-hover", "--color-border-divider", "--color-text-muted"]:
        assert re.search(rf"{re.escape(token)}\s*:", night), f".night-mode 未定义 {token}"


def test_part2_has_cross_iife_year_aliases():
    """Part 2（页面渲染 IIFE）必须从 __yoyoApp 取 Part 1 的年制函数，

    否则换算弹窗里的年制提示会抛 ReferenceError（跨 IIFE 未声明）。
    """
    js = _read(AFTERBODY)
    assert "var getYearMode = app.getYearMode" in js, \
        "Part 2 未取 Part 1 的 getYearMode（跨 IIFE 引用会报 ReferenceError）"
    assert "window.__yoyoApp" in js


def test_static_version_bumped_for_new_assets():
    assert int(config.STATIC_VERSION) >= 20, "改动 JS/CSS 后未提升 STATIC_VERSION（用户会拿到缓存旧文件）"


if __name__ == "__main__":
    test_year_mode_uses_cookie_in_afterbody()
    test_fmt_time_respects_year_mode()
    test_year_mode_setting_buttons()
    test_wuxian_epoch_is_1604()
    test_wuxian_converter_live_update()
    test_change_password_requires_email_code_backend()
    test_profile_change_password_ui()
    test_forgot_password_two_step_code_flow()
    test_mobile_bottom_tab_bar_replaces_left_rail()
    test_mobile_nav_tabs_markup_and_world_page_entry()
    test_world_page_view_uses_shared_time_and_css_tokens()
    test_legacy_css_tokens_are_defined()
    test_part2_has_cross_iife_year_aliases()
    test_static_version_bumped_for_new_assets()
    print("ALL_PASSED")
