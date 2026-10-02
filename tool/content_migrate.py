# -*- coding: utf-8 -*-
"""帖子正文格式迁移：安卓客户端旧 HTML → 用户原文。

背景
----
历史上三端正文的入库格式并不一致：Web 与 Windows 存的一直是用户原文
（Markdown / 纯文本），只有安卓客户端在发帖时把纯文本包装成了 HTML
（`<p>…<br>…</p>`，见安卓端 `PostCreateScreen.toHtml`）。

三端现已统一为「原文入库 + 一律按 Markdown 渲染，HTML 标签按字面文字展示」，
所以库里残留的那批 HTML 正文需要还原成原文，否则会直接显示成 `<p>…</p>` 字面量。

转换规则（与用户确认的口径一致）
--------------------------------
1. `</p>` 紧跟 `<p>`（段落边界）→ 空行；
2. `<br>` / `<br/>` / `<br />` → 换行；
3. 其余 `<p>` / `</p>` 直接删除；
4. HTML 实体反转义（`&lt;` `&gt;` `&amp;` `&quot;` …）——安卓入库前把
   `& < >` 转义过，不还原用户会看到 `&lt;` 字面量；
5. 去掉首尾空白。

只有「含 `<p>` 或 `<br>`」的正文才会被处理，Web / Windows 的普通 Markdown
正文一字不动。

用法
----
    python -m tool.content_migrate --dry-run          # 预览（默认）
    python -m tool.content_migrate --apply            # 写库，自动生成备份
    python -m tool.content_migrate --apply --backup /tmp/bak.jsonl

注意：**只需运行一次**。若某位用户正文里原本就写了字面量 `<p>` / `<br>`，
迁移后结果仍含这些标记，重复运行会被再次转换，所以请勿重复执行。
"""
from __future__ import annotations

import argparse
import html as _html
import json
import re
from datetime import datetime

import db

__all__ = [
    "looks_like_android_html",
    "android_html_to_text",
    "collect_candidates",
    "migrate",
]

# 段落边界：</p> 与 <p> 之间可能夹着换行 / 空白
_PARAGRAPH_BREAK = re.compile(r"</p\s*>\s*<p\s*>", re.IGNORECASE)
_BR = re.compile(r"<br\s*/?>", re.IGNORECASE)
_P_OPEN = re.compile(r"<p\s*>", re.IGNORECASE)
_P_CLOSE = re.compile(r"</p\s*>", re.IGNORECASE)

# 判定「安卓客户端写入的 HTML」：命中任一标记才处理
_HTML_MARK = re.compile(r"<br\s*/?>|<p\s*>|</p\s*>", re.IGNORECASE)


def looks_like_android_html(content) -> bool:
    """正文里是否含安卓客户端写入的 `<p>` / `<br>` 标记。"""
    return bool(content) and bool(_HTML_MARK.search(str(content)))


def android_html_to_text(content) -> str:
    """把安卓客户端写入的 HTML 正文还原为用户原文（Markdown / 纯文本）。

    段边界先转空行，再转 `<br>`、删 `<p>`，最后反转义实体
    （`html.unescape` 是单趟替换，`&amp;lt;` 只会变成 `&lt;`，不会二次解析）。
    """
    if not content:
        return "" if content is None else str(content)
    text = str(content)
    text = _PARAGRAPH_BREAK.sub("\n\n", text)
    text = _BR.sub("\n", text)
    text = _P_OPEN.sub("", text)
    text = _P_CLOSE.sub("", text)
    text = _html.unescape(text)
    return text.strip()


def collect_candidates() -> list:
    """扫描 `posts`，返回**待迁移**条目列表 `[{id, old, new}, …]`。

    只取正文含 `<p>` / `<br>` 的行；转换结果与原值相同的不列入。
    """
    rows = db.execute_query(
        "SELECT id, content FROM posts WHERE content LIKE %s OR content LIKE %s",
        ("%<p>%", "%<br>%"),
        fetch_all=True,
    ) or []
    items = []
    for row in rows:
        content = row.get("content")
        if not looks_like_android_html(content):
            continue
        converted = android_html_to_text(content)
        if converted != content:
            items.append({"id": row.get("id"), "old": content, "new": converted})
    return items


def migrate(apply: bool = False, backup_path: str | None = None, verbose: bool = True) -> dict:
    """执行迁移。

    Args:
        apply:       False 只扫描不写库（默认）；True 先备份再写库
        backup_path: 备份文件路径（JSONL：id + 原始 content）；缺省自动生成
        verbose:     是否打印进度

    Returns:
        {"scanned": n, "updated": n, "ambiguous": n, "backup": path|None}
    """
    def log(msg):
        if verbose:
            print(msg)

    items = collect_candidates()
    report = {"scanned": len(items), "updated": 0, "ambiguous": 0, "backup": None}
    if not items:
        log("[migrate] 没有需要迁移的帖子正文。")
        return report

    # 迁移后仍含 <p>/<br> 的，说明用户原本就写了字面量标签 —— 记录但不阻断
    report["ambiguous"] = sum(1 for it in items if looks_like_android_html(it["new"]))

    if not apply:
        for it in items[:5]:
            log(f"[dry-run] {it['id']}\n  旧: {it['old'][:150]!r}\n  新: {it['new'][:150]!r}")
        log(f"[dry-run] 共 {len(items)} 条待迁移（未写库）；如需执行请加 --apply。")
        return report

    if not backup_path:
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        backup_path = f"content_backup_{stamp}.jsonl"
    with open(backup_path, "w", encoding="utf-8") as fh:
        for it in items:
            fh.write(json.dumps({"id": it["id"], "content": it["old"]},
                                ensure_ascii=False) + "\n")
    report["backup"] = backup_path
    log(f"[migrate] 已备份 {len(items)} 条原文 → {backup_path}")

    for it in items:
        db.execute_query("UPDATE posts SET content = %s WHERE id = %s",
                         (it["new"], it["id"]))
        report["updated"] += 1
    log(f"[migrate] 已更新 {report['updated']} 条帖子正文。")
    return report


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="帖子正文格式迁移：安卓旧 HTML → 原文")
    parser.add_argument("--apply", action="store_true",
                        help="真正写库（默认只扫描预览）")
    parser.add_argument("--dry-run", action="store_true",
                        help="只扫描预览（默认行为，显式给出以便脚本自文档化）")
    parser.add_argument("--backup", default=None, help="备份文件路径（JSONL）")
    args = parser.parse_args(argv)

    report = migrate(apply=args.apply and not args.dry_run, backup_path=args.backup)
    if report["ambiguous"]:
        print(f"[migrate] 提示：{report['ambiguous']} 条正文原本就含字面量 <p>/<br>，"
              f"迁移后仍保留 —— 本次迁移请勿重复执行。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
