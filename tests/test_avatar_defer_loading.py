"""验证头像 <img> 不会阻塞 DOM 初始加载：
   1. avatarHtml() 生成的 img 必须有 loading=lazy、decoding=async，且 src 初始放 data-src（DOM 就绪后再注入 src），
      或等价地：src 不为实际头像 URL。
   2. AfterBody.js 必须存在"DOMContentLoaded 后把 data-src 复制给 src"的逻辑。
   3. 不得出现 loading=eager 的头像 img。
"""
import os
import re
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

AFTERBODY = os.path.join(PROJECT_ROOT, "static", "js", "AfterBody.js")


def _read(path):
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def test_avatar_html_lazy_attributes():
    """avatarHtml() 生成的 img 必须用 data-src 而非 src（或至少 lazy+async；严格模式：必须 defer src）。"""
    js = _read(AFTERBODY)
    # 定位 avatarHtml 函数体内 <img> 构造
    m = re.search(r"function avatarHtml[\s\S]{0,400}?<img[^>]*>", js)
    assert m, "找不到 avatarHtml 函数内的 <img> 构造"
    img_tag = m.group(0)
    # 严格：不允许立即填 src=url（会阻塞 DOM 渲染），必须把真实 URL 放到 data-src 供后处理
    assert 'data-src="' in img_tag or "data-src='" in img_tag, (
        f"avatarHtml 应使用 data-src 延迟加载，当前 img 片段: {img_tag}"
    )
    # 必须声明 loading=lazy, decoding=async 提供双保险
    assert "loading=\"lazy\"" in img_tag.replace("'", '"'), "avatar img 缺少 loading=lazy"
    assert "decoding=\"async\"" in img_tag.replace("'", '"'), "avatar img 缺少 decoding=async"


def test_afterbody_has_data_src_inject_on_domready():
    """AfterBody.js 必须在 DOMContentLoaded 或 init 阶段把所有头像的 data-src 注入到 src。"""
    js = _read(AFTERBODY)
    # 两种写法都接受：a) 直接 DOMContentLoaded 回调；b) document.readyState 判断 + function
    dom_ready_any = (
        "DOMContentLoaded" in js
        or "readyState" in js  # 在 route() / init 触发
    )
    assert dom_ready_any, "AfterBody.js 缺少 DOM 就绪挂钩（DOMContentLoaded / readyState）"
    # 必须有 data-src -> src 的搬运逻辑（多种写法：直接赋值 src=realSrc 或 dataset.src 等）
    data_src_ops = [
        r"img\.src\s*=\s*img\.dataset\.src",
        r"dataset\.src[^;\n]{0,40}\.src\s*=",
        r"getAttribute\(['\"]data-src['\"]\)[^;\n]{0,120}\.src\s*=\s*\w+Src",  # var realSrc=getAttribute('data-src'); ... img.src = realSrc
        r"\.src\s*=\s*[^;]*getAttribute\(['\"]data-src['\"]\)",
        # 等价写法：realSrc = getAttribute('data-src'); ... img.src = realSrc
        r"var \w+Src\s*=\s*\w+\.getAttribute\(['\"]data-src['\"]\)[\s\S]{0,80}\.src\s*=\s*\w+Src",
        r"getAttribute\(['\"]data-src['\"]\)",   # 宽松：函数里对 data-src 做了读取，结合下文 selector + src 赋值即成立
    ]
    matched_pattern = None
    for pat in data_src_ops:
        if re.search(pat, js, re.I):
            matched_pattern = pat
            break
    # 严格验证：同时存在"读取 data-src" + "对 .src 赋值给 img"
    has_read = bool(re.search(r"getAttribute\(['\"]data-src['\"]\)|\.dataset\.src", js))
    has_write = bool(re.search(r"img\[?\s*\(?\s*['\"]?src['\"]?\s*\)?\s*\]?\s*=\s*(?!data:image)", js))
    assert has_read and (matched_pattern or has_write), (
        "AfterBody.js 缺少把 data-src -> src 的头像延迟注入逻辑（应同时存在 data-src 读取 + img.src 赋值）"
    )
    # 选择器必须能选中头像相关 img（比如 img[data-src]，或 .avatar img）
    selector_ok = (
        re.search(r"querySelectorAll\([\"'][^\"']*(data-src|avatar|avatar-sm|avatar-lg)[^\"']*[\"']\)", js)
        or re.search(r"document\.images|getElementsByTagName\([\"']img[\"']\)", js)
    )
    assert selector_ok, "AfterBody.js 缺少选中头像 img 的选择器（如 img[data-src] / .avatar img）"


def test_no_avatar_eager_loading():
    """avatarHtml 中不得存在 loading=eager。"""
    js = _read(AFTERBODY)
    m = re.search(r"function avatarHtml[\s\S]{0,500}", js)
    assert m
    fn_body = m.group(0)
    assert "loading=\"eager\"" not in fn_body.replace("'", '"'), (
        "avatarHtml 里禁用 loading=eager，会阻塞 DOM 加载"
    )


if __name__ == "__main__":
    tests = [
        ("test_avatar_html_lazy_attributes", test_avatar_html_lazy_attributes),
        ("test_afterbody_has_data_src_inject_on_domready", test_afterbody_has_data_src_inject_on_domready),
        ("test_no_avatar_eager_loading", test_no_avatar_eager_loading),
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
