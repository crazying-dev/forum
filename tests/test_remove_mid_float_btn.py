"""验证只保留顶部（面板自带的）世界频道展开按钮，移除中线浮动按钮 world-float-btn。"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def test_html_no_world_float_btn():
    """base.html 里不应再有 id=worldFloatBtn 的按钮元素。"""
    html = (ROOT / "templates" / "base.html").read_text(encoding="utf-8")
    assert 'id="worldFloatBtn"' not in html, \
        "base.html 中仍存在 id=worldFloatBtn 的按钮（中间浮动按钮），需要删除"
    assert "world-float-btn" not in html, \
        "base.html 中仍存在 world-float-btn class"
    print("PASS: HTML 已删除中间浮动按钮")


def test_css_no_world_float_btn():
    """main.css 里不应再存在 .world-float-btn 选择器。"""
    css = (ROOT / "static" / "css" / "main.css").read_text(encoding="utf-8")
    assert ".world-float-btn" not in css, \
        "main.css 中仍包含 .world-float-btn 选择器，需要全部删除"
    print("PASS: CSS 中已清除 world-float-btn")


def test_js_no_world_float_btn():
    """AfterBody.js 里不应再通过 id/变量引用 worldFloatBtn。"""
    js = (ROOT / "static" / "js" / "AfterBody.js").read_text(encoding="utf-8")
    assert "worldFloatBtn" not in js, \
        "AfterBody.js 中仍包含 worldFloatBtn 引用，需清理 floatBtn/syncFloatBtn 相关代码"
    # 不应该有 syncFloatBtn 这个函数（专门用于同步浮动按钮）
    assert "syncFloatBtn" not in js, \
        "AfterBody.js 中仍有 syncFloatBtn 函数/引用"
    print("PASS: JS 已清理浮动按钮逻辑")


def test_top_collapse_button_still_works():
    """CSS 里必须保留 .world-panel.collapsed .world-collapse 的 fixed 浮出规则（顶部按钮）。"""
    from test_world_button_visible import test_css_collapsed_world_collapse_uses_fixed
    test_css_collapsed_world_collapse_uses_fixed()
    print("PASS: 顶部（面板自带的）.world-collapse 浮出规则仍存在")


if __name__ == "__main__":
    test_html_no_world_float_btn()
    test_css_no_world_float_btn()
    test_js_no_world_float_btn()
    test_top_collapse_button_still_works()
    print("ALL_PASSED")
