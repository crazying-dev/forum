"""赞赏码常驻入口（网页端）：页脚 + 设置下拉双双入口，共用一个弹窗。

契约：
* 页脚与设置下拉各有一个 ``[data-support]`` 入口（桌面 / 手机端均可达）
* 两者共用 ``#supportModal`` 弹窗，图片从 ``data-src`` 懒加载
  —— 初始 HTML 不得直接写 ``src``，否则每个页面都会白拉 200KB；
  首次打开后再由浏览器 HTTP 缓存兜住。
"""
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

BASE_TEMPLATE = os.path.join(ROOT, "templates", "base.html")
AFTER_BODY_JS = os.path.join(ROOT, "static", "js", "AfterBody.js")
MAIN_CSS = os.path.join(ROOT, "static", "css", "main.css")
CONFIG_PY = os.path.join(ROOT, "config.py")

QR_URL = "https://img.crazying-dev.top/other/help.png"


def _read(path):
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def test_support_entry_in_footer_and_settings():
    """页脚与设置下拉都应提供「赞赏支持」常驻入口。"""
    html = _read(BASE_TEMPLATE)
    # 只统计真正的属性（data-support>），避免把注释里的 [data-support] 也算进去
    triggers = re.findall(r"\sdata-support>", html)
    assert len(triggers) >= 2, \
        "页脚与设置下拉都应提供 [data-support] 常驻入口，实际 %d 处" % len(triggers)
    assert html.count("赞赏支持") >= 2, "两处入口都应显示「赞赏支持」文案"


def test_support_modal_markup_and_lazy_qr():
    """弹窗容器 + 赞赏码图片必须存在，且图片为懒加载（初始无 src）。"""
    html = _read(BASE_TEMPLATE)
    assert 'id="supportModal"' in html, "缺少赞赏码弹窗容器"
    for token in ('id="supportClose"', 'id="supportCancel"'):
        assert token in html, "赞赏码弹窗缺少关闭元素 %s" % token

    m = re.search(r'<img[^>]*id="supportQr"[^>]*>', html)
    assert m, "找不到 id=supportQr 的赞赏码 <img>"
    tag = m.group(0)
    assert 'data-src="%s"' % QR_URL in tag, \
        "赞赏码图片地址应为 %s" % QR_URL
    # 只允许 data-src，不允许真正的 src（否则每页都下载图片）
    assert re.search(r'(?<![-\w])src=', tag) is None, \
        "赞赏码应懒加载（首次打开才设 src），初始 HTML 不应写 src 属性"


def test_afterbody_wires_support_modal():
    """AfterBody.js 定义并注册 initSupportModal()，并实现 data-src 懒加载。"""
    js = _read(AFTER_BODY_JS)
    assert "function initSupportModal" in js, "AfterBody.js 缺少 initSupportModal()"
    assert re.search(r"^\s*initSupportModal\(\);\s*$", js, re.M), \
        "initSupportModal() 未在 init() 中注册"
    assert "initBugModal();\n    initSupportModal();" in js, \
        "initSupportModal 应紧随 initBugModal 注册"
    assert "getAttribute('data-src')" in js, "应通过 data-src 懒加载赞赏码"
    # 项目硬约束：AfterBody.js 不得出现任何外站域名（赞赏码地址只写在模板的 data-src 上）
    assert "crazying-dev.top" not in js, \
        "AfterBody.js 不得硬编码外站赞赏码地址（应只读 data-src）"


def test_support_styles_present():
    """赞赏码弹窗样式存在（窄屏下不溢出）。"""
    css = _read(MAIN_CSS)
    for token in (".support-text", ".support-qr-wrap", ".support-qr"):
        assert token in css, "main.css 缺少 %s" % token
    assert "max-width: 68vw" in css, "窄屏下赞赏码应限制最大宽度"


def test_static_version_bumped_for_support():
    """改动前端资源后必须 bump STATIC_VERSION。"""
    m = re.search(r'STATIC_VERSION = "(\d+)"', _read(CONFIG_PY))
    assert m, "config.py 缺少 STATIC_VERSION"
    assert int(m.group(1)) >= 34, \
        "本次新增赞赏码弹窗（JS/CSS/模板），STATIC_VERSION 应提升到 >= 34"


if __name__ == "__main__":
    tests = [
        ("test_support_entry_in_footer_and_settings",
         test_support_entry_in_footer_and_settings),
        ("test_support_modal_markup_and_lazy_qr",
         test_support_modal_markup_and_lazy_qr),
        ("test_afterbody_wires_support_modal",
         test_afterbody_wires_support_modal),
        ("test_support_styles_present", test_support_styles_present),
        ("test_static_version_bumped_for_support",
         test_static_version_bumped_for_support),
    ]
    passed = 0
    failed = 0
    for name, fn in tests:
        try:
            fn()
            print("PASS  %s" % name)
            passed += 1
        except AssertionError as e:
            print("FAIL  %s: %s" % (name, e))
            failed += 1
        except Exception as e:  # noqa: BLE001
            print("ERROR %s: %s: %s" % (name, type(e).__name__, e))
            failed += 1
    print("\n%d passed, %d failed" % (passed, failed))
    sys.exit(0 if failed == 0 else 1)
