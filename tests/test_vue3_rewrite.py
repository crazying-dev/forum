"""验证 Vue3 渐进式重写：核心页面由 Vue 应用渲染，Flask 模板仅剩挂载点，
后端 API 与 AfterBody.js 全局能力（导航/主题/Live2D/世界频道）保持不变。"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

PROJECT = ROOT
BASE_HTML = (PROJECT / "templates" / "base.html").read_text(encoding="utf-8")
JS = (PROJECT / "static" / "js" / "AfterBody.js").read_text(encoding="utf-8")
VUE_SRC = PROJECT / "frontend" / "src"

# 页面 → (模板, 入口, 视图)
PAGES = {
    "home": ("index.html", "home.js", "HomeView.vue"),
    "forum": ("forum.html", "forum.js", "ForumView.vue"),
    "post_detail": ("post_detail.html", "post_detail.js", "PostDetailView.vue"),
    "auth": ("auth.html", "auth.js", "AuthView.vue"),
    "users": ("users.html", "users.js", "UserView.vue"),
    "search": ("search.html", "search.js", "SearchView.vue"),
    "post_create": ("post_create.html", "post_create.js", "PostCreateView.vue"),
    "world_page": ("world_page.html", "world_page.js", "WorldPageView.vue"),
    "goto": ("goto.html", "goto.js", "GotoView.vue"),
    "verify_success": ("verify_success.html", "verify_success.js", "VerifySuccessView.vue"),
    "verify_failed": ("verify_failed.html", "verify_failed.js", "VerifyFailedView.vue"),
    "privacy": ("privacy.html", "privacy.js", "PrivacyView.vue"),
    "wiki": ("wiki.html", "wiki.js", "WikiView.vue"),
    "wiki_guanfang": ("wiki_guanfang.html", "wiki_guanfang.js", "WikiGuanfangView.vue"),
    "wiki_personal": ("wiki_personal.html", "wiki_personal.js", "WikiPersonalView.vue"),
    "mouse": ("mouse.html", "mouse.js", "MouseView.vue"),
    "mouse_liunx": ("mouse_liunx.html", "mouse_liunx.js", "MouseLinuxView.vue"),
    "live2d": ("live2d.html", "live2d.js", "Live2DView.vue"),
    "oauth": ("oauth.html", "oauth.js", "OAuthView.vue"),
}


def _read(p: Path) -> str:
    return p.read_text(encoding="utf-8")


def test_templates_mount_vue_app():
    """核心页面模板：包含 #app 挂载点 + data-vue-page 标记 + 对应入口脚本。"""
    for page, (tpl, entry, _view) in PAGES.items():
        html = _read(PROJECT / "templates" / tpl)
        assert 'id="app"' in html, f"{tpl} 缺少 Vue 挂载点 #app"
        assert f'data-vue-page="{page}"' in html, f"{tpl} 缺少 data-vue-page 标记"
        assert f'/static/vue/{entry}?v={{{{ static_version }}}}' in html, \
            f"{tpl} 未引入入口脚本 /static/vue/{entry}"


def test_entries_exist_and_mount():
    """每个入口文件都存在且调用 createApp().mount('#app')。"""
    for _page, (_tpl, entry, _view) in PAGES.items():
        src = _read(VUE_SRC / "entries" / entry)
        assert "createApp" in src and "mount('#app')" in src, f"{entry} 未挂载 Vue 应用"
        assert ".vue'" in src, f"{entry} 未引用对应视图组件"


def test_afterbody_skips_vue_pages():
    """AfterBody.js route() 对 data-vue-page 页面跳过旧页面级初始化，但保留全局能力。"""
    assert "data-vue-page" in JS, "AfterBody.js 未识别 Vue 重写页面的 data-vue-page 标记"
    assert "initGlobalLive2D()" in JS, "route 跳过逻辑丢失了全局 Live2D 初始化"


def test_vue_utils_reuse_afterbody():
    """Vue 共享层复用 AfterBody 的 __yoyoApp（API 去重缓存/时区时间/头像延迟加载）。"""
    utils = _read(VUE_SRC / "utils.js")
    assert "__yoyoApp" in utils, "Vue 工具层未复用 AfterBody 的 __yoyoApp"
    assert "apiFetch" in utils and "resolveAvatarDeferred" in utils, \
        "Vue 工具层缺少 API/头像延迟加载复用"
    assert "CATEGORY_MAP" in utils, "Vue 工具层缺少分类汉化映射"


def test_built_assets_present():
    """构建产物已生成到 static/vue/，模板引用的入口文件必须存在。"""
    dist = PROJECT / "static" / "vue"
    assert dist.is_dir(), "static/vue/ 目录不存在（请先运行 npm run build）"
    for _page, (_tpl, entry, _view) in PAGES.items():
        assert (dist / entry).is_file(), f"构建产物缺失 {entry}（请重新 npm run build）"


def test_base_has_body_attrs_block():
    """base.html 提供 body_attrs 块，供 Vue 页面标记 data-vue-page。"""
    assert "{% block body_attrs %}" in BASE_HTML, "base.html 缺少 body_attrs 块"


if __name__ == "__main__":
    tests = [
        ("test_templates_mount_vue_app", test_templates_mount_vue_app),
        ("test_entries_exist_and_mount", test_entries_exist_and_mount),
        ("test_afterbody_skips_vue_pages", test_afterbody_skips_vue_pages),
        ("test_vue_utils_reuse_afterbody", test_vue_utils_reuse_afterbody),
        ("test_built_assets_present", test_built_assets_present),
        ("test_base_has_body_attrs_block", test_base_has_body_attrs_block),
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
