"""验证 AfterBody.js 完全本地化：不再有任何 CDN / 外站回退引用（资源已全部复制到项目内）。"""
import os
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

AFTERBODY = os.path.join(PROJECT_ROOT, "static", "js", "AfterBody.js")


def _read(path):
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def test_no_external_cdn_references_in_afterbody():
    """AfterBody.js 必须完全本地化：不得包含任何外站 CDN 域名引用。"""
    js = _read(AFTERBODY)
    assert "crazying-dev.top" not in js, "AfterBody.js 仍残留 crazying-dev.top 外站引用"
    for host in ["jsdelivr.net", "unpkg.com", "staticfile.org", "npmmirror.com"]:
        assert host not in js, f"AfterBody.js 仍残留外站域名 {host}"


def test_live2d_local_only():
    """Live2D 主路径必须是同站 /static/live2d/，且不存在 *_CDN 兜底常量。"""
    js = _read(AFTERBODY)
    assert "/static/live2d/HEI.lpk" in js, "主路径 /static/live2d/HEI.lpk 丢失"
    assert "/static/live2d/js/Live2DLPK.js" in js, "主路径 Live2DLPK.js 同站引用丢失"
    assert "/static/live2d/js/jszip.min.js" in js, "同站 JSZip 引用丢失"
    # 不允许再保留任何 CDN 兜底常量
    assert "LPK_CDN" not in js, "不应再存在 LPK_CDN 兜底常量"
    assert "LPKSCRIPT_CDN" not in js, "不应再存在 LPKSCRIPT_CDN 兜底常量"


def test_download_script_uses_cdn_urls():
    """download_live2d_assets.sh 直接从 CDN URL 一次性下载资源到项目（运维用，非运行时依赖）。"""
    sh_path = os.path.join(PROJECT_ROOT, "scripts", "download_live2d_assets.sh")
    assert os.path.isfile(sh_path), "脚本 scripts/download_live2d_assets.sh 缺失"
    sh = _read(sh_path)
    assert "crazying-dev.top" in sh, "下载脚本未使用 CDN URL 前缀"
    assert "/assets/text/one" not in sh, "脚本错误依赖本地 /assets/text/one 目录"
    url_markers = [
        "HEI.lpk",
        "Live2DLPK.js",
        "待机.gif", "嘿咻.gif", "惊醒.gif", "起跳.gif", "铁片.gif",
        "guanfang_cover.webp", "personal_cover.jpg",
    ]
    for m in url_markers:
        assert m in sh, f"下载脚本缺少目标文件名: {m}"


if __name__ == "__main__":
    tests = [
        ("test_no_external_cdn_references_in_afterbody", test_no_external_cdn_references_in_afterbody),
        ("test_live2d_local_only", test_live2d_local_only),
        ("test_download_script_uses_cdn_urls", test_download_script_uses_cdn_urls),
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
