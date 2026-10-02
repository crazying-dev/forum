"""验证客户端发布 / 更新能力：清单 JSON、只读 API、/Download 页面与导航入口。"""
import json
import os
import re
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

MANIFEST_PATH = os.path.join(PROJECT_ROOT, "app_releases.json")
DOWNLOAD_TEMPLATE = os.path.join(PROJECT_ROOT, "templates", "download.html")
BASE_TEMPLATE = os.path.join(PROJECT_ROOT, "templates", "base.html")


# 手机端底部标签栏（.nav-tab）数量基线：新增入口不得走这条通道
# 例外：/Download 在 ≤900px 时头部 .nav-link 与侧栏竖排项均被 main.css 隐藏，
# 手机端仅能通过底部标签栏到达，故计入基线（5 → 6）。
SIDE_NAV_TAB_COUNT = 6


def _read(path):
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def _load_manifest():
    with open(MANIFEST_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def _make_client():
    """构造仅注册 blueprint 的最小 app，不触发 app.py 的 DB / 鉴权中间件。"""
    from flask import Flask

    import api

    app = Flask(
        __name__,
        template_folder=os.path.join(PROJECT_ROOT, "templates"),
        static_folder=os.path.join(PROJECT_ROOT, "static"),
    )
    app.config["JSON_AS_ASCII"] = False
    app.config["TESTING"] = True

    @app.context_processor
    def _inject_globals():
        # base.html 依赖这两个模板变量；缺失时 Jinja Undefined 取值报错，页面会 500
        return {
            "static_version": "test",
            "announcement": {
                "enabled": False,
                "tag": "",
                "text": "",
                "link": "",
                "link_text": "查看详情",
            },
        }

    api.register_blueprints(app)
    return app.test_client()


def test_manifest_file_valid():
    """app_releases.json 必须存在且可解析：schema=1、含 4 个平台、windows 已发布。"""
    assert os.path.isfile(MANIFEST_PATH), f"缺失清单文件: {MANIFEST_PATH}"
    data = _load_manifest()
    assert data.get("schema") == 1, "schema 必须为 1"
    keys = [p.get("key") for p in data.get("platforms") or []]
    for key in ("windows", "android", "linux", "macos"):
        assert key in keys, f"清单缺少平台 {key}"
    windows = next(p for p in data["platforms"] if p.get("key") == "windows")
    assert windows.get("status") == "available", "windows 状态应为 available"
    releases = windows.get("releases") or []
    assert releases, "windows 至少应有 1 个发布版本"
    assert releases[0].get("version"), "windows 发布版本缺少 version"
    assert releases[0].get("url"), "windows 发布版本缺少 url"
    android = next(p for p in data["platforms"] if p.get("key") == "android")
    assert android.get("status") == "available", "android 状态应为 available"
    assert "Android 7.0" in str(android.get("requirement")), "android 系统要求应为 Android 7.0 及以上"


def test_release_api_endpoints():
    """清单 / 单平台 / 版本检查接口行为，含未知平台的 404 分支。"""
    client = _make_client()

    rv = client.get("/api/app/releases")
    body = rv.get_json()
    assert rv.status_code == 200, f"/api/app/releases 状态 {rv.status_code}"
    assert body["success"] is True
    assert len(body["platforms"]) == 4

    rv = client.get("/api/app/releases/windows")
    assert rv.status_code == 200
    assert rv.get_json()["platform"]["key"] == "windows"

    rv = client.get("/api/app/releases/xxx")
    assert rv.status_code == 404
    assert rv.get_json()["success"] is False

    windows = next(p for p in _load_manifest()["platforms"] if p.get("key") == "windows")
    latest = (windows.get("releases") or [{}])[0].get("version")

    rv = client.get("/api/app/check?platform=windows&version=%s" % latest)
    body = rv.get_json()
    assert rv.status_code == 200
    assert body["available"] is False, "已是最新版时不应提示更新"
    assert body["latest"] == latest

    rv = client.get("/api/app/check?platform=windows&version=0.0.1")
    body = rv.get_json()
    assert body["available"] is True
    assert body["latest"] == latest
    assert isinstance(body.get("release"), dict)
    assert body["release"]["version"] == latest
    assert body["message"], "发现新版本时 message 不能为空"

    # 未发布（coming_soon）的平台不应提示可更新
    pending = next(p for p in _load_manifest()["platforms"]
                   if p.get("status") != "available")
    rv = client.get("/api/app/check?platform=%s&version=0.0.1" % pending.get("key"))
    body = rv.get_json()
    assert rv.status_code == 200
    assert body["available"] is False, "coming_soon 平台不应提示可更新"

    rv = client.get("/api/app/check?platform=nope")
    assert rv.status_code == 404
    assert rv.get_json()["success"] is False


def test_download_endpoints_never_500():
    """安装包直链：有包则 200/206，无包必须 503 + JSON，绝不能 500。"""
    client = _make_client()
    for url in ("/api/app/windows/forum.exe", "/api/app/download/windows/forum.exe"):
        rv = client.get(url)
        assert rv.status_code in (200, 206, 503), f"{url} 异常状态 {rv.status_code}"
        if rv.status_code == 503:
            assert rv.get_json()["success"] is False

    rv = client.get("/api/app/download/android/forum.apk")
    assert rv.status_code == 404, "非 windows 平台分发应 404"
    assert rv.get_json()["success"] is False


def test_mirror_endpoint_offline_guards():
    """/api/app/mirror：非法平台 / 文件名 / 无匹配发布必须 404 + JSON，绝不 500。"""
    client = _make_client()
    for url in ("/api/app/mirror/windows/nope.exe",
                "/api/app/mirror/android/forum_setup.exe",
                "/api/app/mirror/windows/_",
                "/api/app/mirror/windows/..%5C..%5Cconfig.py"):
        rv = client.get(url)
        assert rv.status_code == 404, f"{url} 应为 404，实际 {rv.status_code}"
        assert rv.get_json()["success"] is False, f"{url} 应返回 JSON 错误体"
    # 编码斜杠会被 Werkzeug 在路由层拦下（根本进不到视图），同样不能是 500
    assert client.get("/api/app/mirror/windows/..%2F..%2Fconfig.py").status_code == 404


def test_mirror_target_resolves_manifest_url():
    """反代目标解析：命中清单 URL；非 GitHub 主机 / 非法名一律拒绝。"""
    from api.release import _mirror_target

    windows = next(p for p in _load_manifest()["platforms"] if p.get("key") == "windows")
    release = (windows.get("releases") or [{}])[0]
    name = release.get("filename") or "forum_setup.exe"
    target = _mirror_target("windows", name)
    assert target == release.get("url"), "应解析出清单里的 GitHub 直链"
    assert target.startswith("https://github.com/")
    # android 同样可反代（V1.0.4 已发布）；平台与文件名必须同时匹配
    android = next(p for p in _load_manifest()["platforms"] if p.get("key") == "android")
    a_release = (android.get("releases") or [{}])[0]
    a_name = a_release.get("filename")
    assert _mirror_target("android", a_name) == a_release.get("url")
    assert _mirror_target("android", a_name).startswith("https://github.com/")
    assert _mirror_target("android", "forum-android-9.9.9.apk") is None
    assert _mirror_target("linux", "whatever.deb") is None
    assert _mirror_target("android", name) is None
    assert _mirror_target("windows", "../../etc/passwd") is None
    assert _mirror_target("windows", "forum_setup.exe.bak") is None
    assert _mirror_target("windows", "") is None


def test_version_utils():
    """版本号解析 / 比较 / 体积格式化。"""
    from api.release import compare_versions, human_size, parse_version

    assert compare_versions("1.0.0", "1.0.1") < 0
    assert compare_versions("1.10.0", "1.9.0") > 0
    assert compare_versions("2.0", "2.0.0") == 0, "长度不同应按 0 补齐"
    assert parse_version("v1.2.3") == (1, 2, 3)
    assert human_size(48468327).endswith("MB")


def test_download_template_and_manifest_status():
    """下载页模板存在且含未发布态关键字；清单状态与 releases 自洽。"""
    html = _read(DOWNLOAD_TEMPLATE)
    for token in ("coming_soon", "即将推出", "/Download"):
        assert token in html, f"download.html 缺少 {token}"
    for platform in _load_manifest()["platforms"]:
        status = platform.get("status")
        releases = platform.get("releases") or []
        if status == "available":
            assert releases, f"{platform.get('key')} 为 available 时必须有 releases"
        else:
            assert status == "coming_soon", f"{platform.get('key')} 状态非法：{status}"
            assert not releases, f"{platform.get('key')} 未发布时不应有 releases"


def test_android_release_entry():
    """Android 最新版：清单字段与 GitHub Release 直链保持一致。"""
    android = next(p for p in _load_manifest()["platforms"] if p.get("key") == "android")
    release = (android.get("releases") or [{}])[0]
    assert release.get("version") == "1.0.7", "android 版本应为 1.0.7"
    assert release.get("channel") == "stable"
    assert release.get("filename") == "forum-android-1.0.7.apk"
    assert release.get("url") == (
        "https://github.com/crazying-dev/forum/releases/download/"
        "Android-V1.0.7/forum-android-1.0.7.apk")
    assert isinstance(release.get("size"), int) and release["size"] > 0
    assert re.fullmatch(r"[0-9a-f]{64}", str(release.get("sha256"))), "sha256 应为 64 位小写十六进制"
    assert release.get("mandatory") is False


def test_windows_release_entry():
    """Windows 最新版：清单字段与 GitHub Release 直链保持一致。"""
    windows = next(p for p in _load_manifest()["platforms"] if p.get("key") == "windows")
    release = (windows.get("releases") or [{}])[0]
    assert release.get("version") == "1.3.10", "windows 版本应为 1.3.10"
    assert release.get("channel") == "stable"
    assert release.get("filename") == "forum_setup.exe"
    assert release.get("url") == (
        "https://github.com/crazying-dev/forum/releases/download/"
        "Windows-V1.3.10/forum_setup.exe")
    assert isinstance(release.get("size"), int) and release["size"] > 0
    assert re.fullmatch(r"[0-9a-f]{64}", str(release.get("sha256"))), "sha256 应为 64 位小写十六进制"
    assert release.get("mandatory") is False


def test_base_nav_entries():
    """base.html 新增 /Download 入口，且底部标签栏数量稳定（手机端可达性见下）。"""
    html = _read(BASE_TEMPLATE)
    assert 'href="/Download"' in html, "base.html 缺少 /Download 入口"
    count = html.count('class="side-nav-item nav-tab"')
    assert count == SIDE_NAV_TAB_COUNT, f"底部标签栏数量应保持 {SIDE_NAV_TAB_COUNT}，实际 {count}"
    # 手机端（≤900px）头部导航与侧栏竖排项都被隐藏，底部标签栏是唯一入口
    assert 'data-navtab="/Download"' in html, \
        "底部标签栏缺少「下载」入口，手机端将无法进入 /Download"
    css = _read(os.path.join(PROJECT_ROOT, "static", "css", "main.css"))
    assert ".side-nav-item:not(.nav-tab) { display: none; }" in css, \
        "移动端应隐藏侧栏竖排项（否则桌面入口会在窄屏溢出）"
    assert ".header-nav .nav-link { display: none; }" in css, \
        "移动端应隐藏头部导航链接"


def test_download_page_mobile_css():
    """下载页窄屏适配：按钮大点击区 + 长串断行；≤480px 有超窄屏规则。"""
    css = _read(os.path.join(PROJECT_ROOT, "static", "css", "main.css"))
    assert ".dl-actions .btn { flex: 1 1 auto; min-height: 44px; justify-content: center; }" in css, \
        "下载页缺少移动端按钮大点击区规则"
    assert ".dl-notes li, .dl-foot, .dl-requirement { overflow-wrap: anywhere; }" in css, \
        "下载页缺少窄屏长串断行规则（易横向溢出）"
    assert ".dl-tab { flex: 1 1 calc(50% - 3px); justify-content: center; padding: 9px 8px; }" in css, \
        "下载页缺少 ≤480px 平台标签两列均分规则"


def test_download_page_links_use_site_mirror():
    """/Download 的下载按钮 / 复制直链必须指向站内反代路由，而不是 GitHub 直链。"""
    client = _make_client()
    rv = client.get("/Download")
    assert rv.status_code == 200
    html = rv.get_data(as_text=True)

    hrefs = re.findall(r'<a class="btn btn-primary" href="([^"]+)"', html)
    assert hrefs, "下载页没有任何下载按钮"
    for href in hrefs:
        assert "github.com" not in href, f"下载按钮仍指向 GitHub：{href}"
        assert href.startswith("/api/app/mirror/"), f"下载按钮未指向站内反代：{href}"

    copies = re.findall(r'data-copy-url="([^"]+)"', html)
    assert copies, "下载页没有复制直链按钮"
    for url in copies:
        assert "github.com" not in url, f"复制直链仍指向 GitHub：{url}"
        assert url.startswith("/api/app/mirror/"), f"复制直链未指向站内反代：{url}"

    # 两个已发布平台都要有站内入口，并带 ?v= 版本号做缓存失效
    assert "/api/app/mirror/windows/forum_setup.exe?v=1.3.10" in html
    assert "/api/app/mirror/android/forum-android-1.0.7.apk?v=1.0.7" in html


def test_mirror_cache_full_flow():
    """反代缓存：首次填充 → 二次命中（不再回源）→ Range 走内存 → 越界 416 → TTL 过期 → 重启即丢。"""
    import api.release as rel

    payload = b"forum-android-payload-" * 500
    calls = {"n": 0}

    class _Upstream:
        status_code = 200
        headers = {
            "Content-Length": str(len(payload)),
            "Content-Type": "application/octet-stream",
            "ETag": '"etag-1"',
            "Last-Modified": "Wed, 30 Sep 2026 13:35:43 GMT",
        }

        def iter_content(self, size):
            for i in range(0, len(payload), size):
                yield payload[i:i + size]

        def close(self):
            pass

    def _fake_get(url, **kwargs):
        calls["n"] += 1
        return _Upstream()

    android = next(p for p in _load_manifest()["platforms"] if p.get("key") == "android")
    name = (android.get("releases") or [{}])[0].get("filename")
    path = "/api/app/mirror/android/%s" % name

    original = rel.requests.get
    rel.requests.get = _fake_get
    rel.cache_clear()
    try:
        client = _make_client()

        # 1) 首次：回源一次，完整收完后入缓存
        rv = client.get(path)
        assert rv.status_code == 200
        assert rv.get_data() == payload
        assert rv.headers.get("Accept-Ranges") == "bytes"
        assert calls["n"] == 1
        info = rel.cache_info()
        assert info["entries"] == 1 and info["stored"] == 1
        assert info["ttl"] == 24 * 3600, "缓存 TTL 应为 24 小时"

        # 2) 二次：命中缓存，不再回源
        rv = client.get(path)
        assert rv.status_code == 200 and rv.get_data() == payload
        assert calls["n"] == 1, "命中缓存时不应再请求上游"
        assert rel.cache_info()["hit"] == 1

        # 3) Range：从内存切片，206 + Content-Range
        rv = client.get(path, headers={"Range": "bytes=0-9"})
        assert rv.status_code == 206
        assert rv.get_data() == payload[:10]
        assert rv.headers["Content-Range"] == "bytes 0-9/%d" % len(payload)
        assert calls["n"] == 1

        # 4) 末尾 N 字节
        rv = client.get(path, headers={"Range": "bytes=-8"})
        assert rv.status_code == 206
        assert rv.get_data() == payload[-8:]

        # 5) 越界 Range → 416
        rv = client.get(path, headers={"Range": "bytes=9999999-"})
        assert rv.status_code == 416

        # 6) TTL 过期：时间戳前拨 25 小时，下次请求重新回源
        with rel._MIRROR_LOCK:
            for entry in rel._MIRROR_CACHE.values():
                entry["ts"] -= 25 * 3600
        rv = client.get(path)
        assert rv.status_code == 200 and rv.get_data() == payload
        assert calls["n"] == 2, "TTL 过期后应重新回源"

        # 7) 进程重启等价于模块级缓存归零（不落盘）
        assert rel.cache_clear() == 1
        assert rel.cache_info()["entries"] == 0

        # 8) 诊断接口
        rv = client.get("/api/app/cache")
        assert rv.status_code == 200
        assert rv.get_json()["ttl"] == 24 * 3600
    finally:
        rel.requests.get = original
        rel.cache_clear()


def test_download_page_renders():
    """/Download 页面纯服务端渲染成功，含 Windows 与未发布平台文案。"""
    client = _make_client()
    rv = client.get("/Download")
    assert rv.status_code == 200, f"/Download 返回 {rv.status_code}"
    html = rv.get_data(as_text=True)
    assert "即将推出" in html
    assert "Windows" in html


if __name__ == "__main__":
    tests = [
        ("test_manifest_file_valid", test_manifest_file_valid),
        ("test_release_api_endpoints", test_release_api_endpoints),
        ("test_download_endpoints_never_500", test_download_endpoints_never_500),
        ("test_mirror_endpoint_offline_guards", test_mirror_endpoint_offline_guards),
        ("test_mirror_target_resolves_manifest_url", test_mirror_target_resolves_manifest_url),
        ("test_version_utils", test_version_utils),
        ("test_download_template_and_manifest_status", test_download_template_and_manifest_status),
        ("test_android_release_entry", test_android_release_entry),
        ("test_windows_release_entry", test_windows_release_entry),
        ("test_download_page_mobile_css", test_download_page_mobile_css),
        ("test_download_page_links_use_site_mirror", test_download_page_links_use_site_mirror),
        ("test_mirror_cache_full_flow", test_mirror_cache_full_flow),
        ("test_base_nav_entries", test_base_nav_entries),
        ("test_download_page_renders", test_download_page_renders),
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
