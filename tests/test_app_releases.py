"""验证客户端发布 / 更新能力：清单 JSON、只读 API、/Download 页面与导航入口。"""
import json
import os
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

MANIFEST_PATH = os.path.join(PROJECT_ROOT, "app_releases.json")
DOWNLOAD_TEMPLATE = os.path.join(PROJECT_ROOT, "templates", "download.html")
BASE_TEMPLATE = os.path.join(PROJECT_ROOT, "templates", "base.html")


# 手机端底部标签栏（.nav-tab）数量基线：新增入口不得走这条通道
SIDE_NAV_TAB_COUNT = 5


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

    rv = client.get("/api/app/check?platform=android&version=0.0.1")
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


def test_version_utils():
    """版本号解析 / 比较 / 体积格式化。"""
    from api.release import compare_versions, human_size, parse_version

    assert compare_versions("1.0.0", "1.0.1") < 0
    assert compare_versions("1.10.0", "1.9.0") > 0
    assert compare_versions("2.0", "2.0.0") == 0, "长度不同应按 0 补齐"
    assert parse_version("v1.2.3") == (1, 2, 3)
    assert human_size(48468327).endswith("MB")


def test_download_template_and_manifest_status():
    """下载页模板存在且含未发布态关键字；非 windows 平台均为 coming_soon。"""
    html = _read(DOWNLOAD_TEMPLATE)
    for token in ("coming_soon", "即将推出", "/Download"):
        assert token in html, f"download.html 缺少 {token}"
    for platform in _load_manifest()["platforms"]:
        if platform.get("key") != "windows":
            assert platform.get("status") == "coming_soon", f"{platform.get('key')} 应为 coming_soon"


def test_base_nav_entries():
    """base.html 新增 /Download 入口，且不挤占手机端底部标签栏。"""
    html = _read(BASE_TEMPLATE)
    assert 'href="/Download"' in html, "base.html 缺少 /Download 入口"
    count = html.count('class="side-nav-item nav-tab"')
    assert count == SIDE_NAV_TAB_COUNT, f"底部标签栏数量应保持 {SIDE_NAV_TAB_COUNT}，实际 {count}"


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
        ("test_version_utils", test_version_utils),
        ("test_download_template_and_manifest_status", test_download_template_and_manifest_status),
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
