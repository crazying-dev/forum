"""验证 HEI.lpk 配套：Windows 下载脚本存在 + AfterBody.js 完全本地化（无 CDN 兜底）。"""
import os
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


def test_afterbody_lpk_local_only():
    """AfterBody.js 的 HEI.lpk 主路径必须是同站，且不再有 CDN fallback。"""
    js = _read(AFTERBODY_JS)
    assert "/static/live2d/HEI.lpk" in js, "AfterBody.js 缺失同站 HEI.lpk 主路径"
    assert "crazying-dev.top" not in js, "AfterBody.js 不应再引用外站 CDN"


def test_afterbody_js_loader_local_only():
    """AfterBody.js 的 Live2DLPK.js 只从同站加载，无 CDN fallback。"""
    js = _read(AFTERBODY_JS)
    assert "/static/live2d/js/Live2DLPK.js" in js, "AfterBody.js 缺失同站 JS 主路径"
    assert "assets.crazying-dev.top" not in js, "AfterBody.js 不应再引用外站 CDN"
    assert "onerror" in js or "catch" in js, "AfterBody.js 缺少 script.onerror / Promise.catch 错误处理"


if __name__ == "__main__":
    tests = [
        ("test_windows_powershell_download_script_exists", test_windows_powershell_download_script_exists),
        ("test_afterbody_lpk_local_only", test_afterbody_lpk_local_only),
        ("test_afterbody_js_loader_local_only", test_afterbody_js_loader_local_only),
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
