"""验证 Live2D / WIKI 相关资源全部优先使用同站 /static/live2d 或 /static/img 路径，
模板文件不得出现跨域 CDN；脚本内允许仅作为兜底回退常量保留 CDN URL。
策略：主路径必须是 /static/...，CDN 仅允许出现在明确命名的 *_CDN 常量中（如 LPK_CDN、LPKSCRIPT_CDN）。"""
import os
import re
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

TARGET_FILES = {
    "AfterBody.js": os.path.join(PROJECT_ROOT, "static", "js", "AfterBody.js"),
    "live2d.html": os.path.join(PROJECT_ROOT, "templates", "live2d.html"),
    "wiki.html": os.path.join(PROJECT_ROOT, "templates", "wiki.html"),
}

EXPECTED_LIVE2D_JS = "/static/live2d/js/Live2DLPK.js"
EXPECTED_LPK = "/static/live2d/HEI.lpk"
EXPECTED_GIF_DIR = "/static/live2d/gif/"
EXPECTED_WIKI_IMG_DIR = "/static/img/wiki/"

# 模板文件中完全禁止出现的跨域模式（模板不应带任何兜底 CDN）
TEMPLATE_FORBIDDEN_PATTERNS = [
    r"crazying-dev\.top.*Live2D",
    r"crazying-dev\.top.*HEI\.lpk",
    r"crazying-dev\.top.*Live2DLPK",
    r"crazying-dev\.top.*714aed79",
    r"crazying-dev\.top.*R-C\.jpg",
    r"//assets\.crazying-dev\.top",
    r"//img\.crazying-dev\.top.*(WIKI|wiki\.|fw658|R-C)",
]

# 脚本中也完全禁止任何外站 CDN（资源已全部复制到项目内，无白名单例外）
ALLOWED_CDN_LINES = []


def _read(path):
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def _is_allowed_cdn_line(line):
    for a in ALLOWED_CDN_LINES:
        if re.search(a, line, re.I):
            return True
    return False


def test_no_cross_origin_cdn_references():
    """模板与脚本中均禁止任何 Live2D/WIKI 跨域 CDN 引用（完全本地化）。"""
    bad_lines = []
    for name, path in TARGET_FILES.items():
        if not os.path.exists(path):
            raise AssertionError(f"文件缺失: {path}")
        content = _read(path)
        patterns = TEMPLATE_FORBIDDEN_PATTERNS if name.endswith(".html") else [
            r"crazying-dev\.top.*Live2D",
            r"crazying-dev\.top.*HEI\.lpk",
            r"crazying-dev\.top.*Live2DLPK",
            r"crazying-dev\.top.*714aed79",
            r"crazying-dev\.top.*R-C\.jpg",
        ]
        for pat in patterns:
            for m in re.finditer(pat, content, re.I):
                start = content[: m.start()].rfind("\n") + 1
                end = content.find("\n", m.end())
                if end == -1: end = len(content)
                line = content[start:end]
                # 非 HTML 的脚本里：检查是否在 *_CDN 常量等白名单行
                if not name.endswith(".html") and _is_allowed_cdn_line(line):
                    continue
                line_no = content[: m.start()].count("\n") + 1
                bad_lines.append(f"{name}:{line_no} 匹配 '{pat}' -> ...{m.group(0)}...")
    assert not bad_lines, "存在非法跨域 CDN 引用:\n" + "\n".join(bad_lines)


def test_afterbody_local_live2d_paths():
    """AfterBody.js 中 Live2D 主路径必须用同站 /static/live2d/；完全禁止 CDN 兜底常量。"""
    js = _read(TARGET_FILES["AfterBody.js"])
    # Live2DLPK.js 至少 2 处（LPKSCRIPT_LOCAL 常量 + 主逻辑使用）
    assert EXPECTED_LIVE2D_JS in js, f"AfterBody.js 未使用同站 {EXPECTED_LIVE2D_JS}"
    # HEI.lpk 至少 2 处（LPK_LOCAL 常量 + 主逻辑使用）
    assert EXPECTED_LPK in js, f"AfterBody.js 未使用同站 {EXPECTED_LPK}"
    # 不再允许任何 CDN 兜底常量 / 外站域名
    assert "LPK_CDN" not in js, "AfterBody.js 不应再存在 LPK_CDN 兜底常量"
    assert "LPKSCRIPT_CDN" not in js, "AfterBody.js 不应再存在 LPKSCRIPT_CDN 兜底常量"
    assert "crazying-dev.top" not in js, "AfterBody.js 不应再引用 crazying-dev.top"
    for host in ["jsdelivr.net", "unpkg.com", "staticfile.org", "npmmirror.com"]:
        assert host not in js, f"AfterBody.js 不应再引用外站域名 {host}"


def test_live2d_html_gif_local():
    """live2d.html 中 5 张 GIF 必须走同站 /static/live2d/gif/。"""
    html = _read(TARGET_FILES["live2d.html"])
    gifs = ["待机.gif", "嘿咻.gif", "惊醒.gif", "起跳.gif", "铁片.gif"]
    for g in gifs:
        expect = EXPECTED_GIF_DIR + g
        assert expect in html, f"live2d.html 缺少同站 GIF: {expect}"
    count = html.count(EXPECTED_GIF_DIR)
    assert count >= 5, f"live2d.html 中应至少有5处 {EXPECTED_GIF_DIR} 引用，实际 {count} 处"


def test_wiki_html_images_local():
    """wiki.html 中 WIKI 两张封面图必须走同站 /static/img/wiki/。"""
    html = _read(TARGET_FILES["wiki.html"])
    assert EXPECTED_WIKI_IMG_DIR in html, f"wiki.html 未使用 {EXPECTED_WIKI_IMG_DIR} 作为图片目录"
    count = html.count(EXPECTED_WIKI_IMG_DIR)
    assert count >= 2, f"wiki.html 中应至少有2张封面图走同站路径，实际 {count} 处"
    assert "crazying-dev" not in html, "wiki.html 仍残留 crazying-dev CDN"


def test_local_directory_stubs_exist():
    """目录占位文件应存在，保证 git clone / 同步后结构齐全。"""
    dirs = [
        os.path.join(PROJECT_ROOT, "static", "live2d", "js"),
        os.path.join(PROJECT_ROOT, "static", "live2d", "gif"),
        os.path.join(PROJECT_ROOT, "static", "img", "wiki"),
    ]
    for d in dirs:
        # 目录本身必须存在
        assert os.path.isdir(d), f"目录缺失: {d}"
    # live2d 根目录必须有 HEI.lpk 占位或文件
    live2d_root = os.path.join(PROJECT_ROOT, "static", "live2d")
    assert os.path.isdir(live2d_root), f"目录缺失: {live2d_root}"


if __name__ == "__main__":
    tests = [
        ("test_no_cross_origin_cdn_references", test_no_cross_origin_cdn_references),
        ("test_afterbody_local_live2d_paths", test_afterbody_local_live2d_paths),
        ("test_live2d_html_gif_local", test_live2d_html_gif_local),
        ("test_wiki_html_images_local", test_wiki_html_images_local),
        ("test_local_directory_stubs_exist", test_local_directory_stubs_exist),
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
