"""回归：完整版隐私政策 v2.0（三端）+ 网页端自助注销入口 + 评论楼中楼渲染修复。

覆盖：
  1. PrivacyView.vue 为完整版（PIPL 结构、第三方域名逐项、本地存储逐项、联系方式）；
  2. UserView.vue 提供真正可用的注销入口（方式二选一 + 身份验证二选一 + 确认词）；
  3. 构建产物（static/vue/*.js）已随源码重建；
  4. 楼中楼修复：CommentItem 用 .comment-main 包裹，.comment-item 不再是 flex 容器。
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

PROJECT = ROOT
VIEWS = PROJECT / "frontend" / "src" / "views"
COMPONENTS = PROJECT / "frontend" / "src" / "components"
DIST = PROJECT / "static" / "vue"
CSS = (PROJECT / "static" / "css" / "main.css").read_text(encoding="utf-8")


def _read(p: Path) -> str:
    return p.read_text(encoding="utf-8")


PRIVACY = _read(VIEWS / "PrivacyView.vue")
USER_VIEW = _read(VIEWS / "UserView.vue")
COMMENT_ITEM = _read(COMPONENTS / "CommentItem.vue")
POST_DETAIL = _read(VIEWS / "PostDetailView.vue")


# ── 1. 隐私政策完整版 ───────────────────────────────────────

def test_privacy_has_all_sections():
    """十大章节标题都在（引言 + 一~十），否则只是「简版」而非完整版。"""
    headings = [
        "引言与适用范围",
        "我们收集哪些个人信息",
        "我们如何使用你的个人信息",
        "Cookie 与本地存储",
        "第三方服务与信息共享",
        "信息的存储与保存期限",
        "我们如何保护你的信息",
        "未成年人保护",
        "你的权利",
        "本政策的更新",
        "联系我们",
    ]
    missing = [h for h in headings if h not in PRIVACY]
    assert not missing, f"PrivacyView.vue 缺少章节：{missing}"


def test_privacy_meta_and_contact():
    """生效日期 / 联系方式 / 三端适用范围必须明写。"""
    assert "3890320020@qq.com" in PRIVACY, "隐私政策缺少联系邮箱"
    assert "2026 年 10 月 1 日" in PRIVACY, "隐私政策缺少生效日期"
    for client in ("网页端", "Windows", "Android"):
        assert client in PRIVACY, f"隐私政策未声明适用范围包含 {client}"


def test_privacy_lists_third_party_domains():
    """第三方域名必须逐项列出（用户明确要求：域名 + 用途）。"""
    domains = [
        "cdn.jsdelivr.net",
        "dlystc.unknownmp.top",
        "img.crazying-dev.top",
        "qm.qq.com",
        "github.com",
        "ghproxy.net",
        "dns.alidns.com",
        "smtp.163.com",
    ]
    missing = [d for d in domains if d not in PRIVACY]
    assert not missing, f"隐私政策缺少第三方域名：{missing}"


def test_privacy_lists_web_local_storage():
    """网页端 Cookie / localStorage / CacheStorage 键名逐项列出。"""
    keys = [
        "forum-year-mode",
        "forum-theme",
        "forum-announce-dismissed",
        "forum-navmode",
        "forum_world_width",
        "pwa_installed",
        "forum-new-v7",
        "localStorage",
    ]
    missing = [k for k in keys if k not in PRIVACY]
    assert not missing, f"隐私政策缺少本地存储项：{missing}"


def test_privacy_promises_real_self_service_deletion():
    """政策承诺的「自助注销」必须与代码事实一致：两种方式 + 两种验证。"""
    assert "彻底删除" in PRIVACY and "匿名化保留" in PRIVACY, \
        "隐私政策未写明两种注销方式"
    assert "已注销用户" in PRIVACY, "隐私政策未说明匿名化后的用户名"
    import config
    assert config.DELETED_USER_NAME == "已注销用户", \
        "config.DELETED_USER_NAME 与隐私政策文案不一致"
    assert config.DELETE_ACCOUNT_CONFIRM_TEXT == "注销账号", \
        "确认词常量与文档/前端不一致"


# ── 2. 网页端自助注销入口 ───────────────────────────────────

def test_user_view_has_delete_account_panel():
    assert "editPanel === 'delete'" in USER_VIEW, "UserView 缺少注销面板"
    assert "/api/user/delete" in USER_VIEW, "UserView 未调用注销接口"
    assert "/api/email/send-delete-account-code" in USER_VIEW, \
        "UserView 未调用注销验证码接口"


def test_user_view_delete_modes_and_verification():
    assert "'purge'" in USER_VIEW and "'anonymize'" in USER_VIEW, \
        "注销方式必须提供 purge / anonymize 两个选项"
    assert "delVerify" in USER_VIEW and "delPassword" in USER_VIEW and "delCode" in USER_VIEW, \
        "身份验证必须支持密码或邮箱验证码二选一"
    assert "注销账号" in USER_VIEW, "缺少「注销账号」确认词输入"


def test_user_view_me_is_reactive():
    """me 必须响应式：否则登录态晚到时「编辑资料 / 注销」入口永远不出现。"""
    assert "const me = ref(getCurrentUser())" in USER_VIEW, \
        "UserView 的 me 应为 ref（响应式）"
    assert "initAuth" in USER_VIEW, "UserView 应在挂载时等待登录态就绪"


# ── 3. 构建产物 ─────────────────────────────────────────────

def test_built_assets_regenerated():
    """源码改动后必须重新 npm run build（否则用户拿到的还是旧产物）。"""
    for name, min_size in (("privacy.js", 8000), ("users.js", 12000)):
        f = DIST / name
        assert f.is_file(), f"缺少构建产物 {name}（请运行 npm run build）"
        assert f.stat().st_size >= min_size, \
            f"{name} 体积异常（{f.stat().st_size}B），可能未包含新内容"


def test_static_version_bumped_for_privacy_v2():
    import config
    assert int(config.STATIC_VERSION) >= 35, \
        "改动 PrivacyView / UserView / main.css 后必须 bump config.STATIC_VERSION"


# ── 4. 楼中楼渲染修复（Bug：子评论排版 / 未渲染）─────────────

def test_comment_item_wraps_main_block():
    """头像与正文包进 .comment-main；.comment-children 是 .comment-item 的直接子块。"""
    assert 'class="comment-main"' in COMMENT_ITEM, "CommentItem 缺少 .comment-main 包裹层"
    assert COMMENT_ITEM.index('class="comment-main"') < COMMENT_ITEM.index('class="comment-children"'), \
        "子评论块必须位于 .comment-main 之外（否则会被排成横向 flex 兄弟项）"


def test_css_comment_item_not_flex_container():
    assert ".comment-item { display: block; }" in CSS, \
        ".comment-item 必须为块级容器（原 display:flex 会把子评论排成一行）"
    assert ".comment-main { display: flex;" in CSS, ".comment-main 应承担横向头像+正文布局"


def test_comment_tree_labels_reply_target():
    """子评论要显示「回复 @某人」，必须由父节点回填昵称。"""
    assert "reply_to_name" in POST_DETAIL, "commentTree 未标注被回复人昵称"
    assert "reply_to_uid" in POST_DETAIL, "commentTree 未标注被回复人 ID"
    assert "parent.children.push(c)" in POST_DETAIL, "commentTree 未构建父子关系"


if __name__ == "__main__":
    tests = [
        ("test_privacy_has_all_sections", test_privacy_has_all_sections),
        ("test_privacy_meta_and_contact", test_privacy_meta_and_contact),
        ("test_privacy_lists_third_party_domains", test_privacy_lists_third_party_domains),
        ("test_privacy_lists_web_local_storage", test_privacy_lists_web_local_storage),
        ("test_privacy_promises_real_self_service_deletion", test_privacy_promises_real_self_service_deletion),
        ("test_user_view_has_delete_account_panel", test_user_view_has_delete_account_panel),
        ("test_user_view_delete_modes_and_verification", test_user_view_delete_modes_and_verification),
        ("test_user_view_me_is_reactive", test_user_view_me_is_reactive),
        ("test_built_assets_regenerated", test_built_assets_regenerated),
        ("test_static_version_bumped_for_privacy_v2", test_static_version_bumped_for_privacy_v2),
        ("test_comment_item_wraps_main_block", test_comment_item_wraps_main_block),
        ("test_css_comment_item_not_flex_container", test_css_comment_item_not_flex_container),
        ("test_comment_tree_labels_reply_target", test_comment_tree_labels_reply_target),
    ]
    passed = failed = 0
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
