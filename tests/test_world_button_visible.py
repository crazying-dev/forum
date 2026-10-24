"""验证世界频道展开按钮：只保留顶部（面板自带）浮出按钮，不再有中间浮动按钮。"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def test_css_collapsed_world_collapse_uses_fixed():
    """桌面端 CSS 里必须有 .world-panel.collapsed 下 .world-collapse 的 fixed/absolute 定位。"""
    css = (ROOT / "static" / "css" / "main.css").read_text(encoding="utf-8")
    pattern = re.compile(
        r"\.world-panel\.collapsed\s*\.world-collapse\s*\{[^}]*position\s*:\s*(?:fixed|absolute)",
        re.DOTALL,
    )
    assert pattern.search(css), (
        "main.css 里缺少桌面端规则 '.world-panel.collapsed .world-collapse { position: fixed/absolute }'；"
        "面板收起后宽度为 0，自带按钮会不可见。"
    )
    print("PASS: world-collapse 在 collapsed 下有 fixed/absolute 定位")


def test_html_no_mid_float_button():
    """HTML 中不应再存在 id=worldFloatBtn（中间浮动按钮已删除）。"""
    html = (ROOT / "templates" / "base.html").read_text(encoding="utf-8")
    assert 'id="worldFloatBtn"' not in html and "world-float-btn" not in html, \
        "base.html 中仍保留 worldFloatBtn 中间浮动按钮元素"
    print("PASS: HTML 中没有中间浮动按钮 worldFloatBtn")


def test_css_no_world_float_btn_selector():
    """CSS 中不再允许任何 .world-float-btn 选择器。"""
    css = (ROOT / "static" / "css" / "main.css").read_text(encoding="utf-8")
    assert ".world-float-btn" not in css, \
        "main.css 中仍有 .world-float-btn 残留选择器"
    print("PASS: CSS 中没有 .world-float-btn 选择器残留")


if __name__ == "__main__":
    test_css_collapsed_world_collapse_uses_fixed()
    test_html_no_mid_float_button()
    test_css_no_world_float_btn_selector()
    print("ALL_PASSED")
