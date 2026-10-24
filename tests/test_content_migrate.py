# -*- coding: utf-8 -*-
"""回归：帖子正文格式统一为「用户原文 + 一律 Markdown 渲染」。

背景：三端入库口径不一致 —— Web / Windows 存 Markdown 原文，只有安卓客户端
把纯文本包装成 `<p>…<br>…</p>`，并且安卓端读的时候走 HtmlCompat 按 HTML 渲染。
本次统一后：
* 安卓发帖不再包装 HTML，原文直传；
* 三端一律按 Markdown 渲染，HTML 标签按字面文字展示；
* 历史安卓 HTML 正文由 ``tool/content_migrate.py`` 还原成原文。

本文件覆盖两部分：纯转换函数（不碰 DB）+ 前端/配置侧的静态断言。
"""
from __future__ import annotations

import os
import sys
import json
from pathlib import Path

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

from tool import content_migrate as cm  # noqa: E402


# ────────────── 判定：只看含 <p> / <br> 的正文 ──────────────

def test_looks_like_android_html():
    assert cm.looks_like_android_html("<p>正文</p>")
    assert cm.looks_like_android_html("a<br>b")
    assert cm.looks_like_android_html("a<br/>b")
    assert cm.looks_like_android_html("a<BR />b")


def test_plain_markdown_is_not_android_html():
    for text in ("", None, "# 标题\n\n正文段落", "- 列表项", "AT&T 真香", "a < b > c"):
        assert not cm.looks_like_android_html(text), f"不应误判：{text!r}"


# ────────────── 转换规则 ──────────────

def test_paragraph_boundary_becomes_blank_line():
    """`</p><p>` → 空行；`<br>` → 换行；其余 p 标签删除。"""
    assert cm.android_html_to_text("<p>a<br>b</p><p>c</p>") == "a\nb\n\nc"


def test_br_variants_and_case():
    assert cm.android_html_to_text("<p>a<br/>b<br />c<BR>d</p>") == "a\nb\nc\nd"


def test_entities_are_unescaped():
    """安卓入库前把 & < > 转义过，必须还原，否则用户看到 &lt; 字面量。"""
    out = cm.android_html_to_text("<p>&lt;div&gt; &amp; &quot;q&quot;</p>")
    assert out == '<div> & "q"'


def test_double_escaped_is_single_pass():
    """`&amp;lt;` 只能变成 `&lt;`，不能被二次解析成 `<`。"""
    assert cm.android_html_to_text("<p>&amp;lt;</p>") == "&lt;"


def test_at_and_t_survives_round_trip():
    assert cm.android_html_to_text("<p>AT&amp;T</p>") == "AT&T"


def test_whitespace_trimmed():
    assert cm.android_html_to_text("  <p>a</p>  ") == "a"


def test_multi_paragraph_realistic_sample():
    raw = "<p>第一段<br>换行</p><p>第二段 &amp; 收尾</p>"
    assert cm.android_html_to_text(raw) == "第一段\n换行\n\n第二段 & 收尾"


# ────────────── collect_candidates / migrate（DB 全部 mock） ──────────────

class _FakeDB:
    """记录调用的假 db，只支持 execute_query。"""

    def __init__(self, rows):
        self.rows = rows
        self.selects = 0
        self.updates = []

    def execute_query(self, query, params=None, fetch_all=False, fetch=False):
        assert "<p>%" in query or "LIKE" in query, f"意外查询：{query}"
        self.selects += 1
        return list(self.rows)


class _FakeDBWithUpdate:
    def __init__(self, rows):
        self.rows = rows
        self.updates = []
        self.queries = []

    def execute_query(self, query, params=None, fetch_all=False, fetch=False):
        self.queries.append((query, params))
        if query.strip().upper().startswith("UPDATE"):
            self.updates.append(params)
            return 1
        return list(self.rows)


_ROWS = [
    {"id": "P1", "content": "<p>a<br>b</p><p>c</p>"},
    {"id": "P2", "content": "# 已经就是 Markdown\n\n不用动"},
    {"id": "P3", "content": "<p>只有一段</p>"},
    {"id": "P4", "content": None},
]


def test_collect_candidates_filters_and_diffs(monkeypatch):
    fake = _FakeDB(_ROWS)
    monkeypatch.setattr(cm.db, "execute_query", fake.execute_query)
    items = cm.collect_candidates()
    assert [it["id"] for it in items] == ["P1", "P3"]
    assert items[0]["new"] == "a\nb\n\nc"
    assert items[1]["new"] == "只有一段"


def test_migrate_dry_run_never_writes(monkeypatch, capsys):
    fake = _FakeDBWithUpdate(_ROWS)
    monkeypatch.setattr(cm.db, "execute_query", fake.execute_query)
    report = cm.migrate(apply=False)
    assert report["scanned"] == 2 and report["updated"] == 0
    assert fake.updates == [], "dry-run 绝不能写库"
    assert report["backup"] is None


def test_migrate_apply_writes_and_backs_up(monkeypatch, tmp_path):
    fake = _FakeDBWithUpdate(_ROWS)
    monkeypatch.setattr(cm.db, "execute_query", fake.execute_query)
    backup = tmp_path / "bak.jsonl"
    report = cm.migrate(apply=True, backup_path=str(backup))

    assert report["updated"] == 2
    assert report["backup"] == str(backup)
    assert fake.updates == [("a\nb\n\nc", "P1"), ("只有一段", "P3")]

    lines = [json.loads(l) for l in backup.read_text(encoding="utf-8").splitlines() if l.strip()]
    assert [l["id"] for l in lines] == ["P1", "P3"]
    assert lines[0]["content"] == "<p>a<br>b</p><p>c</p>"


def test_migrate_no_candidates_is_noop(monkeypatch):
    fake = _FakeDBWithUpdate([{"id": "P2", "content": "纯 Markdown"}])
    monkeypatch.setattr(cm.db, "execute_query", fake.execute_query)
    report = cm.migrate(apply=True)
    assert report == {"scanned": 0, "updated": 0, "ambiguous": 0, "backup": None}
    assert fake.updates == []


def test_ambiguous_rows_are_counted(monkeypatch, tmp_path):
    """用户原本就写了字面量 <p> 时，迁移后仍含标记 → 计数提醒。"""
    rows = [{"id": "PX", "content": "<p>&lt;p&gt;字面量&lt;/p&gt;</p>"}]
    fake = _FakeDBWithUpdate(rows)
    monkeypatch.setattr(cm.db, "execute_query", fake.execute_query)
    report = cm.migrate(apply=True, backup_path=str(tmp_path / "b.jsonl"))
    assert report["ambiguous"] == 1 and report["updated"] == 1


# ────────────── 前端 / 配置侧静态断言 ──────────────

def _read(rel: str) -> str:
    return (Path(PROJECT_ROOT) / rel).read_text(encoding="utf-8")


def test_afterbody_disables_html_rendering():
    """网页端必须在 marked 上覆写 html 渲染器，把 HTML 当字面文字。"""
    js = _read("static/js/AfterBody.js")
    assert "marked.use(" in js, "缺少 marked.use 覆写"
    assert "renderer:" in js and "html: function" in js, "缺少 html 渲染器覆写"
    assert "_escapeHtmlLiteral" in js, "HTML 字面量转义函数缺失"
    # breaks 单换行即换行必须保留（三端统一口径）
    assert "breaks: true" in js


def test_static_version_bumped_for_markdown_change():
    import config
    assert int(config.STATIC_VERSION) >= 38, \
        f"改动 AfterBody.js 后必须 bump STATIC_VERSION（当前 {config.STATIC_VERSION}）"


def test_service_worker_cache_bumped():
    sw = _read("static/sw.js")
    assert "CACHE_NAME = 'forum-new-v8'" in sw, "AfterBody.js 改了，SW 缓存名必须升级"


def test_post_row_comment_keeps_markdown_policy():
    """入库侧注释应说明「原文直传、不包装 HTML」。"""
    src = _read("db/post.py")
    assert "原样入库" in src and "content_migrate" in src


def test_android_client_stops_wrapping_html():
    """安卓端发帖不得再把正文包装成 HTML。"""
    rel = "../forum-Android/app/src/main/java/top/crazying/forum/ui/screens/PostCreateScreen.kt"
    p = (Path(PROJECT_ROOT) / rel).resolve()
    if not p.exists():
        import pytest
        pytest.skip("同仓库旁的 forum-Android 不存在（CI 单独 checkout 时跳过）")
    src = p.read_text(encoding="utf-8")
    assert "createPost(t, c, category)" in src, "发帖必须原样直传正文"
    assert "createPost(t, toHtml(c), category)" not in src, "不得再包 HTML"
