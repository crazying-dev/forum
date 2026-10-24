"""V2 公告组件 + 去除叶羽/旧中文分类 key 的契约测试。

背景：用户在 V2 正式上架前提出「去除叶羽 / 加入公告组件 / 修复不适配 V2 的部分」：
  1. 去除叶羽：V1/V2 均无「叶羽」分区（库里 0 篇），全站不再出现该 key；
  2. 公告组件①：发帖页「发帖须知」合规卡片（对照 V1 .post-compliance-notice）；
  3. 公告组件②：全站公告横幅（config.SITE_ANNOUNCEMENT_*，可配置可关闭）；
  4. 清除旧版 V2 中文分类 key（叶羽/创意/求助）兼容映射。

约定：
  - 分类口径只有 5 个 V1 英文 key（general/talk/question/share/creative）；
  - 横幅文案留空或 SITE_ANNOUNCEMENT_ENABLED=0 时整个横幅不渲染；
  - 关闭记忆以「标签+文案」为 key 存 localStorage（forum-announce-dismissed）。
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

PROJECT = ROOT
VUE_SRC = PROJECT / "frontend" / "src"

CREATE_VUE = (VUE_SRC / "views" / "PostCreateView.vue").read_text(encoding="utf-8")
UTILS_JS = (VUE_SRC / "utils.js").read_text(encoding="utf-8")
CSS = (PROJECT / "static" / "css" / "main.css").read_text(encoding="utf-8")
JS = (PROJECT / "static" / "js" / "AfterBody.js").read_text(encoding="utf-8")
BASE_HTML = (PROJECT / "templates" / "base.html").read_text(encoding="utf-8")
POST_API = (PROJECT / "api" / "post" / "__init__.py").read_text(encoding="utf-8")
APP_PY = (PROJECT / "app.py").read_text(encoding="utf-8")
CONFIG_PY = (PROJECT / "config.py").read_text(encoding="utf-8")


# ── A1 发帖页「发帖须知」合规卡片（对照 V1 结构 + 8 条规则）──
def test_post_compliance_notice_in_create_view():
    for cls in ("post-compliance-notice", "post-compliance-header", "post-compliance-list"):
        assert cls in CREATE_VUE, f"发帖页缺少发帖须知类名 .{cls}"
    assert "发帖须知" in CREATE_VUE, "发帖页缺少「发帖须知」标题"
    # 卡片应位于 <form> 内、标题表单组之前（对照 V1 摆放位置）
    assert "<form @submit.prevent=\"submit\">" in CREATE_VUE, "发帖页表单结构变化"
    idx_form = CREATE_VUE.index("<form @submit.prevent=\"submit\">")
    idx_notice = CREATE_VUE.index("post-compliance-notice")
    idx_title = CREATE_VUE.index("<label>标题</label>")
    assert idx_form < idx_notice < idx_title, "发帖须知应作为表单首个子块（在标题之前）"
    # 至少 8 条规则
    m = re.search(r"post-compliance-list\">(.*?)</ul>", CREATE_VUE, re.S)
    assert m, "发帖页未找到发帖须知规则列表"
    lis = re.findall(r"<li>.*?</li>", m.group(1), re.S)
    assert len(lis) >= 8, f"发帖须知规则应有 ≥ 8 条（对照 V1），实际 {len(lis)}"
    for kw in ("法律法规", "政治敏感", "人身攻击", "广告", "隐私", "知识产权", "罗小黑", "封禁"):
        assert kw in m.group(1), f"发帖须知缺少规则关键词「{kw}」"


# ── A2 发帖须知的样式（V2 设计令牌，非 V1 变量）──
def test_post_compliance_notice_css():
    assert ".post-compliance-notice {" in CSS, "缺少 .post-compliance-notice 样式"
    assert ".post-compliance-header" in CSS, "缺少 .post-compliance-header 样式"
    assert ".post-compliance-list" in CSS, "缺少 .post-compliance-list 样式"
    assert "var(--color-primary)" in CSS, "发帖须知未使用 V2 主题色令牌"
    # 发帖须知样式块自身不应回引 V1 旧变量名
    block = CSS.split(".post-compliance-notice {", 1)[1]
    block = block.split("/* ──", 1)[0]
    assert "--color-bg-item-hover" not in block, "发帖须知误用 V1 变量 --color-bg-item-hover"


# ── B1 全站公告横幅的配置项（config.SITE_ANNOUNCEMENT_*）──
def test_site_announcement_config():
    import config
    assert isinstance(config.SITE_ANNOUNCEMENT_ENABLED, bool), "SITE_ANNOUNCEMENT_ENABLED 应为布尔"
    assert config.SITE_ANNOUNCEMENT_TAG, "SITE_ANNOUNCEMENT_TAG 默认值不应为空"
    assert config.SITE_ANNOUNCEMENT_TEXT, "SITE_ANNOUNCEMENT_TEXT 默认值不应为空"
    assert hasattr(config, "SITE_ANNOUNCEMENT_LINK"), "缺少 SITE_ANNOUNCEMENT_LINK"
    assert config.SITE_ANNOUNCEMENT_LINK_TEXT, "SITE_ANNOUNCEMENT_LINK_TEXT 默认值不应为空"
    # 可用环境变量关闭（文案留空 / ENABLED=0）
    assert 'os.getenv("SITE_ANNOUNCEMENT_ENABLED", "1")' in CONFIG_PY, \
        "公告开关应可用环境变量 SITE_ANNOUNCEMENT_ENABLED 覆盖"
    assert '"SITE_ANNOUNCEMENT_TEXT"' in CONFIG_PY, \
        "公告文案应可用环境变量 SITE_ANNOUNCEMENT_TEXT 覆盖"


# ── B2 公告上下文处理器注入模板变量 announcement ──
def test_site_announcement_context_processor():
    assert "_inject_announcement" in APP_PY, "app.py 缺少 _inject_announcement 上下文处理器"
    assert "@app.context_processor" in APP_PY, "缺少 context_processor 装饰器"
    m = re.search(r"def _inject_announcement\(\):(.*?)\n\n", APP_PY, re.S)
    assert m, "未找到 _inject_announcement 函数体"
    body = m.group(1)
    for field in ("enabled", "tag", "text", "link", "link_text"):
        assert f'"{field}"' in body, f"公告上下文缺少字段 {field}"


# ── B3 公告横幅模板（base.html：全站页头下方渲染 + 可关闭）──
def test_site_announcement_banner_markup():
    assert "{% if announcement.enabled and announcement.text %}" in BASE_HTML, \
        "base.html 缺少公告渲染开关（enabled 且 text 非空）"
    assert 'class="site-announce"' in BASE_HTML and 'id="siteAnnounce"' in BASE_HTML, \
        "base.html 缺少 .site-announce 横幅容器"
    assert 'id="siteAnnounceClose"' in BASE_HTML, "base.html 缺少公告关闭按钮"
    assert "data-announce-key" in BASE_HTML, "缺少 data-announce-key（关闭记忆依据「标签+文案」）"
    assert "forum-announce-dismissed" in BASE_HTML, "缺少 localStorage 关闭记忆 key"
    assert "localStorage" in BASE_HTML, "公告关闭记忆未使用 localStorage"
    # 横幅应位于 </header> 之后、侧边栏之前
    idx_header = BASE_HTML.index("</header>")
    idx_banner = BASE_HTML.index('id="siteAnnounce"')
    idx_side = BASE_HTML.index('class="side-nav"')
    assert idx_header < idx_banner < idx_side, "公告横幅应紧跟在页头之后渲染"


# ── B4 公告横幅样式 ──
def test_site_announcement_css():
    for sel in (".site-announce {", ".site-announce-tag", ".site-announce-text",
                ".site-announce-close"):
        assert sel in CSS, f"缺少公告横幅样式 {sel}"
    assert "max-width: 1100px" in CSS.split(".site-announce {", 1)[1].split("}", 1)[0], \
        "公告横幅宽度应与 .layout 对齐（max-width: 1100px）"
    assert "@media (max-width: 900px)" in CSS and ".site-announce { width: calc(100% - 20px); margin: 8px 10px 0; }" in CSS, \
        "缺少移动端公告横幅适配"


# ── C1 去除叶羽 + 清除旧中文分类 key 兼容映射 ──
def test_legacy_category_keys_fully_removed():
    import config
    assert "叶羽" not in config.ALLOWED_CATEGORIES, "config 白名单仍含「叶羽」"
    # utils.js：旧中文 key 与兼容导出均移除
    assert "CATEGORY_LEGACY" not in UTILS_JS, "utils.js 仍存在 CATEGORY_LEGACY"
    assert "叶羽" not in UTILS_JS, "utils.js 仍出现「叶羽」"
    assert "创意" not in UTILS_JS, "utils.js 仍出现「创意」"
    # AfterBody.js：兼容映射的 key 不再有旧中文（注意「求助」仅作为 question 的值）
    m = re.search(r"var CATEGORY_MAP = \{([^}]+)\};", JS)
    assert m, "AfterBody.js 未找到 CATEGORY_MAP"
    body = m.group(1)
    for legacy in ("叶羽", "创意"):
        assert f"'{legacy}':" not in body, f"AfterBody.js 映射仍残留旧 key '{legacy}':"
    assert "'求助':" not in body, "AfterBody.js 映射仍残留旧 key '求助':"
    # 邮件分类名不再用旧叫法
    assert "叶羽" not in POST_API, "api/post/__init__.py 仍出现「叶羽」"
    for old in ("综合讨论", "创意工坊", "求助提问"):
        assert old not in POST_API, f"邮件仍在使用旧叫法「{old}」"


if __name__ == "__main__":
    tests = [
        ("test_post_compliance_notice_in_create_view", test_post_compliance_notice_in_create_view),
        ("test_post_compliance_notice_css", test_post_compliance_notice_css),
        ("test_site_announcement_config", test_site_announcement_config),
        ("test_site_announcement_context_processor", test_site_announcement_context_processor),
        ("test_site_announcement_banner_markup", test_site_announcement_banner_markup),
        ("test_site_announcement_css", test_site_announcement_css),
        ("test_legacy_category_keys_fully_removed", test_legacy_category_keys_fully_removed),
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
