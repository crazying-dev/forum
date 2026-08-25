"""验证全局 Live2D 浮动组件的结构（模板 + CSS + JS）"""
import os
import re
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

BASE_HTML = os.path.join(PROJECT_ROOT, "templates", "base.html")
MAIN_CSS = os.path.join(PROJECT_ROOT, "static", "css", "main.css")
AFTERBODY_JS = os.path.join(PROJECT_ROOT, "static", "js", "AfterBody.js")


def _read(path):
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def test_base_html_has_global_live2d_container():
    """非 Live2D 页面应渲染全局 Live2D 容器（带条件判断 show_global_live2d）。"""
    html = _read(BASE_HTML)
    # 必须存在全局 Live2D 容器
    assert "global-live2d" in html, "base.html 缺少 id='global-live2d' 的全局 Live2D 容器"
    # 必须用条件包裹，排除 Live2D 本页面
    cond_markers = ["show_global_live2d", "Live2D"]
    found = any(m in html for m in ["show_global_live2d", "request.path != '/Live2D'", "pathname !== '/Live2D'"])
    assert found, "base.html 中全局 Live2D 必须被条件包裹，以排除 /Live2D 页面"


def test_global_live2d_css_position():
    """全局 Live2D 容器必须 position:fixed 放在右下角，z-index 低（背景层上方）。"""
    css = _read(MAIN_CSS)
    # 必须有 #global-live2d 或 .global-live2d 样式
    assert re.search(r"[#\.]global-live2d", css), "main.css 缺少 global-live2d 样式"
    # 固定定位 + 右下角
    block_match = re.search(r"[#\.]global-live2d\s*\{[^}]*\}", css, re.S)
    assert block_match, "main.css 中找不到 global-live2d 样式块"
    block = block_match.group(0)
    assert "position" in block and "fixed" in block, "global-live2d 必须使用 position:fixed"
    assert "bottom" in block or "right" in block, "global-live2d 必须定位在右下角（要有 bottom/right）"
    # z-index：必须低（背景层上方，< 10，header z=100、world-panel z=95）
    z_match = re.search(r"z-index\s*:\s*(\d+)", block)
    assert z_match, "global-live2d 必须设置 z-index"
    z_val = int(z_match.group(1))
    assert z_val < 10, f"global-live2d z-index 必须很低（背景层上方，<10），当前为 {z_val}"
    assert z_val >= 1, f"global-live2d z-index 至少 >=1 才能在背景色之上，当前为 {z_val}"


def test_afterbody_has_global_live2d_init():
    """AfterBody.js 中必须有全局 Live2D 初始化函数，并排除 /Live2D 页面。"""
    js = _read(AFTERBODY_JS)
    assert "global-live2d" in js, "AfterBody.js 缺少 global-live2d 相关逻辑"
    # 排除 Live2D 页面判断
    assert "Live2D" in js, "AfterBody.js 应在非 Live2D 页面才初始化全局 Live2D"
    # 存在鼠标跟随/视角追踪逻辑（全屏范围监听）
    assert "mousemove" in js, "AfterBody.js 缺少全屏 mousemove 视角跟随监听"


def test_live2d_page_explicitly_disabled():
    """live2d.html（/Live2D 路由）不显示全局浮动 Live2D，由后端传参控制。"""
    # 检查 pages_bp 中 /Live2D 是否传参 show_global_live2d=False
    pages_py = os.path.join(PROJECT_ROOT, "api", "pages", "__init__.py")
    py = _read(pages_py)
    assert "show_global_live2d" in py or "show_world" in py, (
        "/Live2D 路由应明确设置参数以禁用全局 Live2D"
    )
    # 若使用 show_global_live2d=False 或者通过模板判断路径均可


if __name__ == "__main__":
    tests = [
        ("test_base_html_has_global_live2d_container", test_base_html_has_global_live2d_container),
        ("test_global_live2d_css_position", test_global_live2d_css_position),
        ("test_afterbody_has_global_live2d_init", test_afterbody_has_global_live2d_init),
        ("test_live2d_page_explicitly_disabled", test_live2d_page_explicitly_disabled),
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
        except Exception as e:
            print(f"ERROR {name}: {type(e).__name__}: {e}")
            failed += 1
    print(f"\n{passed} passed, {failed} failed")
    sys.exit(0 if failed == 0 else 1)
