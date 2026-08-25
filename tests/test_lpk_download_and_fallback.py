"""验证 HEI.lpk 配套：Windows 下载脚本存在 + AfterBody.js fallback CDN 兜底逻辑。"""
import os
import re
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

AFTERBODY_JS = os.path.join(PROJECT_ROOT, "static", "js", "AfterBody.js")
PS_SCRIPT = os.path.join(PROJECT_ROOT, "scripts", "download_live2d_assets.ps1")
SH_SCRIPT = os.path.join(PROJECT_ROOT, "scripts", "download_live2d_assets.sh")


def _read(path):
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def test_windows_powershell_download_script_exists():
    """scripts/download_live2d_assets.ps1 必须存在，并含 HEI.lpk / Live2DLPK.js / GIF / WIKI 封面下载逻辑。"""
    assert os.path.isfile(PS_SCRIPT), f"缺失 Windows 下载脚本: {PS_SCRIPT}"
    ps = _read(PS_SCRIPT)
    for key in ["HEI.lpk", "Live2DLPK.js", "待机.gif", "guanfang_cover", "personal_cover", "crazying-dev"]:
        assert key in ps, f"PowerShell 脚本缺少对 '{key}' 的下载逻辑"
    # bash 脚本也继续保留
    assert os.path.isfile(SH_SCRIPT), "缺失 Linux bash 下载脚本"


def test_afterbody_lpk_fallback_cdn_on_missing_local():
    """AfterBody.js 在本地 /static/live2d/HEI.lpk 下载失败时必须回退 CDN URL。"""
    js = _read(AFTERBODY_JS)
    # 主路径是同站 /static/live2d/HEI.lpk
    assert "/static/live2d/HEI.lpk" in js, "AfterBody.js 缺失同站 HEI.lpk 主路径"
    # fallback CDN URL 必须存在（本地文件缺失时的兜底）
    assert re.search(r"assets\.crazying-dev\.top.*HEI\.lpk", js), (
        "AfterBody.js 未提供 HEI.lpk 的 CDN fallback 逻辑"
    )
    # 必须能看出"失败 → 回退"结构：.catch 或者 onError 里切换 URL 再重试
    has_catch = "catch" in js and ("retry" in js.lower() or "fallback" in js.lower() or "cdn" in js.lower()
                                     or "crazying-dev" in js)
    assert has_catch, "AfterBody.js 未实现 catch/失败重试 → fallback 的结构"


def test_afterbody_js_loader_fallback_cdn():
    """AfterBody.js 在本地 /static/live2d/js/Live2DLPK.js 加载失败（onerror）时必须 fallback 到 CDN。"""
    js = _read(AFTERBODY_JS)
    assert "/static/live2d/js/Live2DLPK.js" in js, "AfterBody.js 缺失同站 JS 主路径"
    assert re.search(r"assets\.crazying-dev\.top.*Live2DLPK\.js", js), (
        "AfterBody.js 未提供 Live2DLPK.js 的 CDN fallback"
    )
    # onerror 或 .catch 中触发 fallback
    assert "onerror" in js or "catch" in js, "AfterBody.js 缺少 script.onerror / Promise.catch 错误处理"


if __name__ == "__main__":
    tests = [
        ("test_windows_powershell_download_script_exists", test_windows_powershell_download_script_exists),
        ("test_afterbody_lpk_fallback_cdn_on_missing_local", test_afterbody_lpk_fallback_cdn_on_missing_local),
        ("test_afterbody_js_loader_fallback_cdn", test_afterbody_js_loader_fallback_cdn),
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
