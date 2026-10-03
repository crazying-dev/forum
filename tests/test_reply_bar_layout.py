"""回归测试：点击「回复 @xxx」时，回复横幅必须独占一行，不得挤压评论输入框。

曾经的问题（用户反馈）：网页端点「回复某人」后，`.reply-bar`（回复 @xxx：…）宽度
几乎占满整行，「发表评论」按钮宽度不变，导致 textarea 被压缩到极小；手机版与
电脑端均有此问题。

根因（纯 CSS flex 计算）：`.comment-input` 是单行 flex 容器；`.reply-bar` 的
`width: 100%` 使其 flex-basis 等于整行宽度 W，textarea 的 `flex: 1` 基数为 0，
按钮 `flex-shrink: 0`。基数合计为 W + 0 + 按钮宽 + gap > W，进入收缩阶段后
全部压缩量都被分摊到「有基数」的 .reply-bar 上，于是 textarea 被压成 0 宽。

修复：`.comment-input` 允许换行（flex-wrap: wrap）；`.reply-bar` 用
`flex: 1 1 100%` 独占第一行，textarea + 按钮换行到第二行，与无回复时的布局一致。
"""
import os
import re
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

CSS_PATH = os.path.join(PROJECT_ROOT, "static", "css", "main.css")
VUE_VIEW = os.path.join(PROJECT_ROOT, "frontend", "src", "views", "PostDetailView.vue")
CONFIG_PATH = os.path.join(PROJECT_ROOT, "config.py")


# 修复要求的最小静态版本号（改动 main.css 后必须 ≥ 此值做缓存失效）
MIN_STATIC_VERSION = 39


def _read(path):
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def _rule(css, selector):
    """精确匹配选择器 `selector` 的第一条规则体（不含花括号）。

    用 `\\s*\\{` 收尾可避免把 `.reply-bar button { ... }` 误当成 `.reply-bar`。
    """
    m = re.search(re.escape(selector) + r"\s*\{([^}]*)\}", css)
    return m.group(1) if m else ""


def test_comment_input_allows_wrap():
    """.comment-input 必须允许换行，否则回复横幅会把输入框挤出第二行。"""
    body = _rule(_read(CSS_PATH), ".comment-input")
    assert body, "main.css 中找不到 .comment-input 规则"
    assert "display" in body and "flex" in body, ".comment-input 应仍是 flex 容器"
    assert re.search(r"flex-wrap\s*:\s*wrap", body), \
        ".comment-input 缺少 flex-wrap: wrap，回复横幅无法换行，会挤压 textarea"


def test_reply_bar_takes_full_first_line():
    """.reply-bar 必须 flex:1 1 100% 独占一行，并带 min-width:0 允许收缩。"""
    body = _rule(_read(CSS_PATH), ".reply-bar")
    assert body, "main.css 中找不到 .reply-bar 规则"
    assert re.search(r"flex\s*:\s*1\s+1\s+100%", body), \
        ".reply-bar 应为 flex: 1 1 100%（独占第一行，不参与 input + 按钮那一行的收缩）"
    assert re.search(r"min-width\s*:\s*0", body), \
        ".reply-bar 缺少 min-width: 0，长用户名可能撑破容器"


def test_reply_bar_is_inside_comment_input():
    """结构保障：.reply-bar 必须仍是 .comment-input 的直接子元素。"""
    vue = _read(VUE_VIEW)
    ci = vue.find('class="comment-input"')
    rb = vue.find('class="reply-bar"')
    ta = vue.find('<textarea id="commentContent"')
    # 按钮用 @click="submitComment" 定位（脚本里还有 function submitComment()，不能直接搜名字）
    btn = vue.find('@click="submitComment"')
    assert ci != -1, "PostDetailView.vue 找不到 .comment-input 容器"
    assert rb != -1, "PostDetailView.vue 找不到 .reply-bar 横幅"
    assert ta != -1 and btn != -1, "PostDetailView.vue 找不到 textarea / 发表评论按钮"
    assert ci < rb < ta < btn, \
        "DOM 顺序应为 .comment-input → .reply-bar → textarea → 发表评论按钮"


def test_static_version_bumped():
    """main.css 已改动，STATIC_VERSION 必须 ≥ %d 才能让浏览器重新拉取。""" % MIN_STATIC_VERSION
    src = _read(CONFIG_PATH)
    m = re.search(r'STATIC_VERSION\s*=\s*"(\d+)"', src)
    assert m is not None, "config.py 找不到 STATIC_VERSION"
    assert int(m.group(1)) >= MIN_STATIC_VERSION, \
        f"STATIC_VERSION={m.group(1)} 未递增（要求 ≥ {MIN_STATIC_VERSION}），用户会拿到旧 CSS"


if __name__ == "__main__":
    tests = [
        ("test_comment_input_allows_wrap", test_comment_input_allows_wrap),
        ("test_reply_bar_takes_full_first_line", test_reply_bar_takes_full_first_line),
        ("test_reply_bar_is_inside_comment_input", test_reply_bar_is_inside_comment_input),
        ("test_static_version_bumped", test_static_version_bumped),
    ]
    passed = 0
    failed = 0
    for name, fn in tests:
        try:
            fn()
            print(f"PASS  {name}")
            passed += 1
        except AssertionError as e:
            print(f"FAIL  {name}: {e}")
            failed += 1
    print(f"\n{passed} passed, {failed} failed")
    sys.exit(1 if failed else 0)
