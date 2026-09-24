"""V2 帖子分区（分类）对照 V1 重译的契约测试。

背景：V2 论坛分区 tab / 发帖选项此前使用中文 key（叶羽/创意/求助），
与 V1 及库里存量帖子的英文 key（talk/question/share/creative 等）不一致。
列表接口是精确匹配（db/post.py: AND p.category = %s），导致：
  - 「求助」tab 只能筛出 2 篇，而 72 篇 question 帖子虽显示「求助」却不进该 tab；
  - 「创意」tab 15 篇 creative 帖子不可见；
  - 闲聊(talk,144) / 分享(share,47) / 创作(creative,15) 根本没有入口。

约定（对照 V1，四处必须完全一致）：
  1. config.ALLOWED_CATEGORIES
  2. frontend/src/views/ForumView.vue        论坛分区 tab
  3. frontend/src/views/PostCreateView.vue   发帖选项
  4. static/js/AfterBody.js + frontend/src/utils.js  CATEGORY_MAP
另：api/post/__init__.py 邮件里的分类名与页面标签保持同一套叫法。
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

PROJECT = ROOT
VUE_SRC = PROJECT / "frontend" / "src"

# V1 权威口径（forum/main/templates/forum.html + post_create.html + AfterBody.js CATEGORY_LABELS）
V1_CATEGORIES = [
    ("general", "综合"),
    ("talk", "闲聊"),
    ("question", "求助"),
    ("share", "分享"),
    ("creative", "创作"),
]
V1_ORDER = [k for k, _ in V1_CATEGORIES]

FORUM_VUE = (VUE_SRC / "views" / "ForumView.vue").read_text(encoding="utf-8")
CREATE_VUE = (VUE_SRC / "views" / "PostCreateView.vue").read_text(encoding="utf-8")
UTILS_JS = (VUE_SRC / "utils.js").read_text(encoding="utf-8")
AFTERBODY_JS = (PROJECT / "static" / "js" / "AfterBody.js").read_text(encoding="utf-8")
POST_API = (PROJECT / "api" / "post" / "__init__.py").read_text(encoding="utf-8")


# ── P1 config 白名单与 V1 一致，且不再出现「叶羽」 ──
def test_config_allowed_categories_align_v1():
    import config
    assert config.ALLOWED_CATEGORIES == V1_ORDER, \
        f"ALLOWED_CATEGORIES 应为 V1 口径 {V1_ORDER}，实际 {config.ALLOWED_CATEGORIES}"
    assert "叶羽" not in config.ALLOWED_CATEGORIES, \
        "「叶羽」在库里 0 篇且 V1 无此分区，不应保留在白名单"


# ── P2 论坛分区 tab 集合/顺序/标签与 V1 一致 ──
def test_forum_tabs_align_v1():
    m = re.search(r"const categories = \[(.*?)\]", FORUM_VUE, re.S)
    assert m, "ForumView.vue 未找到 categories 定义"
    pairs = re.findall(r"key:\s*'([^']*)',\s*label:\s*'([^']*)'", m.group(1))
    assert pairs, "ForumView.vue categories 解析失败"
    assert pairs[0] == ("", "全部"), f"论坛首个 tab 应为「全部」，实际 {pairs[0]}"
    assert pairs[1:] == V1_CATEGORIES, \
        f"论坛分区 tab 应为 V1 口径 {V1_CATEGORIES}，实际 {pairs[1:]}"


# ── P3 发帖页分类选项与 V1 一致 ──
def test_post_create_options_align_v1():
    m = re.search(r'<select v-model="category">(.*?)</select>', CREATE_VUE, re.S)
    assert m, "PostCreateView.vue 未找到分类 select"
    pairs = re.findall(r'<option value="([^"]+)">([^<]+)</option>', m.group(1))
    assert pairs == V1_CATEGORIES, f"发帖分类选项应为 V1 口径 {V1_CATEGORIES}，实际 {pairs}"
    assert "const category = ref('general')" in CREATE_VUE, "发帖默认分类应为 general"


# ── P4 Vue 工具层 CATEGORY_MAP ──
def test_utils_category_map_align_v1():
    for key, label in V1_CATEGORIES:
        assert re.search(rf"\b{key}:\s*'{label}'", UTILS_JS), \
            f"utils.js CATEGORY_MAP 缺少 {key} → {label}"
    # 历史遗留中文 key 兼容（旧版 V2 帖子仍能正确汉化，不会露出原始 key）
    assert re.search(r"创意:\s*'创作'", UTILS_JS), "utils.js 兼容映射 创意 应显示为「创作」"
    assert re.search(r"叶羽:\s*'叶羽'", UTILS_JS), "utils.js 兼容映射缺少 叶羽"
    assert "export const CATEGORY_MAP" in UTILS_JS, "utils.js 未导出 CATEGORY_MAP"


# ── P5 静态脚本 AfterBody.js CATEGORY_MAP（列表卡片/详情页汉化） ──
def test_afterbody_category_map_align_v1():
    m = re.search(r"var CATEGORY_MAP = \{([^}]+)\};", AFTERBODY_JS)
    assert m, "AfterBody.js 未找到 CATEGORY_MAP"
    body = m.group(1)
    for key, label in V1_CATEGORIES:
        assert f"'{key}': '{label}'" in body, \
            f"AfterBody.js CATEGORY_MAP 缺少 '{key}': '{label}'"
    assert "'创意': '创作'" in body, "AfterBody.js 兼容映射 创意 应显示为「创作」"


# ── P6 邮件分类名与页面标签统一（不再有旧叫法） ──
def test_email_category_name_align_page_labels():
    m = re.search(r"_CATEGORY_NAME_MAP = \{(.*?)\}", POST_API, re.S)
    assert m, "api/post/__init__.py 未找到 _CATEGORY_NAME_MAP"
    body = m.group(1)
    for key, label in V1_CATEGORIES:
        assert f'"{key}": "{label}"' in body, f"邮件分类名缺少 {key} → {label}"
    for old in ("综合讨论", "创意工坊", "求助提问"):
        assert old not in POST_API, f"邮件仍在使用旧叫法「{old}」"


# ── P7 列表分区为精确匹配 + API 解析 category 参数 ──
def test_post_list_category_exact_match():
    dbsrc = (PROJECT / "db" / "post.py").read_text(encoding="utf-8")
    assert "AND p.category = %s" in dbsrc, \
        "列表分区筛选应为精确匹配（用 V1 英文 key 才能筛出全部帖子）"
    assert 'request.args.get("category")' in POST_API, "/api/posts 未解析 category 参数"


# ── P8 改动静态资源后版本号已 bump（浏览器缓存失效） ──
def test_static_version_bumped():
    import config
    assert int(config.STATIC_VERSION) >= 18, \
        "改动 AfterBody.js / Vue 产物后必须 bump config.STATIC_VERSION（当前 " + str(config.STATIC_VERSION) + "）"


if __name__ == "__main__":
    tests = [
        ("test_config_allowed_categories_align_v1", test_config_allowed_categories_align_v1),
        ("test_forum_tabs_align_v1", test_forum_tabs_align_v1),
        ("test_post_create_options_align_v1", test_post_create_options_align_v1),
        ("test_utils_category_map_align_v1", test_utils_category_map_align_v1),
        ("test_afterbody_category_map_align_v1", test_afterbody_category_map_align_v1),
        ("test_email_category_name_align_page_labels", test_email_category_name_align_page_labels),
        ("test_post_list_category_exact_match", test_post_list_category_exact_match),
        ("test_static_version_bumped", test_static_version_bumped),
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
        except Exception as e:  # noqa: BLE001
            print(f"ERROR {name}: {type(e).__name__}: {e}")
            failed += 1
    print(f"\n{passed} passed, {failed} failed")
    sys.exit(0 if failed == 0 else 1)
