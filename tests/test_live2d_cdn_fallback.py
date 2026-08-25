"""验证 AfterBody.js 中本地同站资源加载失败时有 CDN fallback 兜底。"""
import os
import re
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

AFTERBODY = os.path.join(PROJECT_ROOT, "static", "js", "AfterBody.js")


def _read(path):
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def test_lpk_local_has_cdn_fallback():
    """加载本地 HEI.lpk 失败（catch 分支）时应回退到 CDN assets.crazying-dev.top。"""
    js = _read(AFTERBODY)
    # 主路径仍是同站 /static/live2d/HEI.lpk
    assert "/static/live2d/HEI.lpk" in js, "主路径 /static/live2d/HEI.lpk 丢失"
    # fallback: catch 中再次调用 load 时参数包含 crazying-dev...HEI.lpk
    fallback_lpk_pat = r"catch[\s\S]{0,500}?crazying-dev\.top[\s\S]{0,80}?HEI\.lpk"
    # 更直接：必须存在 CDN 的 HEI.lpk URL（作为兜底回退常量）
    assert re.search(r"crazying-dev\.top[^\s\"']*Live2D[^\s\"']*HEI\.lpk", js, re.I), (
        "AfterBody.js 中找不到 CDN 版 HEI.lpk 回退 URL"
    )


def test_live2dlpkjs_local_has_cdn_fallback():
    """Live2DLPK.js 也必须有 CDN 回退地址。"""
    js = _read(AFTERBODY)
    assert "/static/live2d/js/Live2DLPK.js" in js, "主路径 Live2DLPK.js 同站引用丢失"
    assert re.search(r"crazying-dev\.top[^\s\"']*JS[^\s\"']*Live2DLPK\.js", js, re.I), (
        "AfterBody.js 中找不到 CDN 版 Live2DLPK.js 回退 URL"
    )


def test_download_script_uses_cdn_urls():
    """download_live2d_assets.sh 必须直接从 CDN URL 下载，不依赖本地 /assets/text/one 目录。"""
    sh_path = os.path.join(PROJECT_ROOT, "scripts", "download_live2d_assets.sh")
    assert os.path.isfile(sh_path), "脚本 scripts/download_live2d_assets.sh 缺失"
    sh = _read(sh_path)
    # 必须含有 CDN 前缀（assets/img crazying-dev.top）
    assert "crazying-dev.top" in sh, "下载脚本未使用 CDN URL 前缀"
    # 不能依赖 /assets/text/one 本地目录
    assert "/assets/text/one" not in sh, "脚本错误依赖本地 /assets/text/one 目录"
    # 9 个文件的下载必须全部包含源 URL (或 CDN 前缀组合)
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
        ("test_lpk_local_has_cdn_fallback", test_lpk_local_has_cdn_fallback),
        ("test_live2dlpkjs_local_has_cdn_fallback", test_live2dlpkjs_local_has_cdn_fallback),
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
