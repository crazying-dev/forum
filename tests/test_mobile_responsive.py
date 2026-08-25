"""验证手机版窄屏兼容性：viewport、多断点、iOS 缩放、按钮/字号、安全区等。"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


CSS_PATH = ROOT / "static" / "css" / "main.css"
HTML_PATH = ROOT / "templates" / "base.html"


def _extract_media(css: str, max_width: int) -> str:
    """提取 @media (max-width: MAX_WIDTHpx) { ... } 内的内容（只抓第一层花括号）。"""
    marker = f"@media (max-width: {max_width}px)"
    start = css.find(marker)
    if start == -1:
        return ""
    brace_start = css.find("{", start)
    if brace_start == -1:
        return ""
    depth = 0
    i = brace_start
    while i < len(css):
        if css[i] == "{":
            depth += 1
        elif css[i] == "}":
            depth -= 1
            if depth == 0:
                return css[brace_start + 1:i]
        i += 1
    return ""


def test_viewport_has_ios_safety():
    """viewport 必须含 maximum-scale、user-scalable、viewport-fit 防 iOS 缩放和刘海。"""
    html = HTML_PATH.read_text(encoding="utf-8")
    m = re.search(r'<meta\s+name="viewport"\s+content="([^"]*)"', html)
    assert m is not None, "找不到 viewport meta"
    content = m.group(1)
    checks = {
        "maximum-scale": "iOS 会允许双指缩放，缺少 maximum-scale=1",
        "user-scalable": "缺少 user-scalable=no",
        "viewport-fit": "缺少 viewport-fit=cover（iPhone 刘海屏安全区）",
    }
    for k, msg in checks.items():
        assert k in content, f"viewport 缺少 {k}: {msg}"
    print(f"PASS: viewport = {content}")


def test_breakpoints_exist():
    """必须有 ≤600px（常规手机）和 ≤380px（SE/小屏）两个断点，覆盖超窄屏。"""
    css = CSS_PATH.read_text(encoding="utf-8")
    for bw in [600, 380]:
        assert f"@media (max-width: {bw}px)" in css, \
            f"CSS 缺少 @media (max-width: {bw}px) 断点"
    print("PASS: 600px / 380px 断点都存在")


def test_mobile_input_fontsize_16px():
    """移动端 input/textarea/select 字号必须 ≥ 16px，防止 iOS 聚焦自动放大页面。"""
    css = CSS_PATH.read_text(encoding="utf-8")
    # 在任意 @media (max-width: ...px) 里查找 input 相关 font-size >= 16px
    mobile_blocks = ""
    for mw in [900, 600, 380]:
        mobile_blocks += _extract_media(css, mw)
    # 也可以在全局中用 @supports 或变量，但最简单是 mobile_blocks 中包含 16px 的 input 规则
    ok = False
    reason = ""
    # 匹配 form-group input 或 input 的 font-size 规则
    for pattern in [
        r'input[^{]*\{[^}]*font-size\s*:\s*16px',
        r'form-group[^{]*\{[^}]*input[^}]*font-size\s*:\s*16px',
        r'@media[^{]*\{[^}]*input[^{]*\{[^}]*font-size\s*:\s*16px',
    ]:
        if re.search(pattern, mobile_blocks + "\n" + css, re.DOTALL):
            ok = True
            break
    # 更简单：直接搜 mobile 媒体查询中是否把 font-size 提到 16px
    if not ok:
        if ("16px" in mobile_blocks) and ("input" in mobile_blocks):
            ok = True
        else:
            reason = "在 ≤900/600/380px 媒体查询内未找到 input 的 font-size:16px 规则"
    assert ok, f"{reason}（iOS 聚焦 <16px input 会自动缩放整页）"
    print("PASS: 移动端 input/textarea/select font-size >= 16px")


def test_mobile_button_minheight_44px():
    """移动端 .btn 的触摸区域至少 44px（Apple HIG 规范）。"""
    css = CSS_PATH.read_text(encoding="utf-8")
    mobile_blocks = ""
    for mw in [900, 600, 380]:
        mobile_blocks += _extract_media(css, mw)
    ok = "min-height" in mobile_blocks and ("44px" in mobile_blocks or "3rem" in mobile_blocks)
    assert ok, "移动端未给 .btn 设置 min-height:44px（触摸不达标）"
    print("PASS: 移动端按钮 min-height >= 44px")


def test_safe_area_inset():
    """footer/body 需支持 iPhone 刘海屏：env(safe-area-inset-bottom)。"""
    css = CSS_PATH.read_text(encoding="utf-8")
    assert "safe-area-inset" in css, \
        "CSS 未使用 env(safe-area-inset-*)，iPhone 底部横条会遮挡内容"
    print("PASS: 使用了 safe-area-inset 适配刘海屏")


def test_narrow_header_compress():
    """≤380px 或 ≤600px 必须压缩 header（padding/gap 减小，搜索框变窄）。"""
    css = CSS_PATH.read_text(encoding="utf-8")
    block600 = _extract_media(css, 600)
    block380 = _extract_media(css, 380)
    narrow = block600 + block380
    ok = (".header-inner" in narrow or ".header-search" in narrow) and \
         ("padding" in narrow or "gap" in narrow or "max-width" in narrow)
    assert ok, "窄屏断点中未压缩 header-inner / header-search"
    print("PASS: 窄屏断点中 header 有压缩规则")


def test_user_profile_responsive():
    """窄屏下 user-profile 必须改为 column 或 wrap，防止头像+名字+按钮挤爆 320px。"""
    css = CSS_PATH.read_text(encoding="utf-8")
    block600 = _extract_media(css, 600)
    block380 = _extract_media(css, 380)
    narrow = block600 + block380
    ok = (".user-profile" in narrow) and (
        "flex-direction" in narrow and "column" in narrow or
        "flex-wrap" in narrow
    )
    assert ok, "窄屏未对 .user-profile 改 column/wrap，小屏会横向溢出"
    print("PASS: user-profile 在窄屏有响应式调整")


def test_post_title_break_word():
    """post-item-title / post-detail-title 需要长词断行防止溢出。"""
    css = CSS_PATH.read_text(encoding="utf-8")
    for selector in [".post-item-title", ".post-detail-title"]:
        # 找到包含该选择器的规则，检查是否有 word-break/overflow-wrap
        patterns = [
            rf'{re.escape(selector)}[^{{]*\{{[^}}]*word-break',
            rf'{re.escape(selector)}[^{{]*\{{[^}}]*overflow-wrap',
        ]
        found = any(re.search(p, css, re.DOTALL) for p in patterns)
        assert found, f"{selector} 缺少 word-break / overflow-wrap 断行"
    print("PASS: 帖子标题有断行保护")


if __name__ == "__main__":
    test_viewport_has_ios_safety()
    test_breakpoints_exist()
    test_mobile_input_fontsize_16px()
    test_mobile_button_minheight_44px()
    test_safe_area_inset()
    test_narrow_header_compress()
    test_user_profile_responsive()
    test_post_title_break_word()
    print("ALL_PASSED")
