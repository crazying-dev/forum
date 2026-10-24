#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""forum-legacy (forum_user) -> yj-forum-ouo (forum_user2) 数据迁移。

特点：
  * 源库只读；目标库可自动创建、自动应用 ouo 迁移（0001-0028）。
  * 幂等：可重复执行（ON CONFLICT / 自然键去重）。
  * 默认 dry-run，必须加 --apply 才写。
  * 不迁移：sessions / verify_tokens / verify_codes（临时数据）、
    comment_reports / post_view_log（ouo 无对应表）。

用法：
  export SOURCE_DATABASE_URL='postgresql://user:pass@127.0.0.1:5432/forum_user'
  export TARGET_DATABASE_URL='postgresql://user:pass@127.0.0.1:5432/forum_user2'

  python3 scripts/migrate_legacy_to_ouo.py --create-db --apply
"""

import argparse
import json
import os
import sys
from pathlib import Path

import psycopg2
from psycopg2 import extras
from psycopg2.extensions import parse_dsn


CATEGORY_MAP = {"求助": "question", "创意": "creative"}
PAGE = 1000


def conn(dsn, autocommit=False):
    # dsn 支持连接串或 parse_dsn() 返回的 dict（建库时需要用 dict 改 dbname）
    c = psycopg2.connect(**dsn) if isinstance(dsn, dict) else psycopg2.connect(dsn)
    c.autocommit = autocommit
    with c.cursor() as cur:
        cur.execute("SET TIME ZONE 'UTC'")
    c.commit()
    return c


def ensure_database(target_dsn):
    info = parse_dsn(target_dsn)
    dbname = info.get("dbname")
    if not dbname:
        sys.exit("TARGET_DATABASE_URL 缺少 dbname")
    admin = dict(info)
    admin["dbname"] = "postgres"
    c = conn(admin, autocommit=True)
    try:
        with c.cursor() as cur:
            cur.execute("SELECT 1 FROM pg_database WHERE datname=%s", (dbname,))
            if cur.fetchone():
                print(f"[db] {dbname} 已存在")
                return False
            ident = '"' + dbname.replace('"', '""') + '"'
            cur.execute(f"CREATE DATABASE {ident} ENCODING 'UTF8' TEMPLATE template0")
            print(f"[db] 已创建 {dbname}")
            return True
    finally:
        c.close()


def apply_migrations(target, migrations_dir):
    files = sorted(Path(migrations_dir).glob("*.up.sql"))
    if not files:
        sys.exit(f"迁移目录为空: {migrations_dir}")
    with target.cursor() as cur:
        cur.execute("SELECT to_regclass('public.schema_migrations')")
        exists = cur.fetchone()[0] is not None
        current = 0
        if exists:
            cur.execute("SELECT version, dirty FROM schema_migrations LIMIT 1")
            row = cur.fetchone()
            if row:
                current, dirty = int(row[0]), bool(row[1])
                if dirty:
                    sys.exit("目标库 schema_migrations dirty=true，请先人工修复后再迁移")
        else:
            cur.execute(
                "CREATE TABLE schema_migrations (version bigint NOT NULL PRIMARY KEY, dirty boolean NOT NULL)"
            )
            print("[schema] 已创建 schema_migrations")

        applied = 0
        latest = current
        for path in files:
            version = int(path.name.split("_", 1)[0])
            if version <= current:
                continue
            sql = path.read_text(encoding="utf-8")
            cur.execute(sql)
            applied += 1
            latest = version
            print(f"[schema] 应用 {path.name}")

        if applied:
            cur.execute("DELETE FROM schema_migrations")
            cur.execute(
                "INSERT INTO schema_migrations(version, dirty) VALUES (%s, false)", (latest,)
            )
    target.commit()
    print(f"[schema] 完成，当前版本 {latest}（本次应用 {applied} 个）")


def insert_many(cur, sql, rows, page=PAGE):
    if not rows:
        return 0
    extras.execute_values(cur, sql, rows, page_size=page)
    return len(rows)


def map_age(v):
    if v is None or v == 0:
        return ""
    return str(v)


def map_category(v):
    if not v:
        return "general"
    return CATEGORY_MAP.get(v, v)


def run(source, target, args):
    src = source.cursor()
    dst = target.cursor()
    report = []

    def count(cur, table):
        cur.execute(f"SELECT count(*) FROM {table}")
        return cur.fetchone()[0]

    # ---------- users ----------
    src.execute(
        "SELECT id,name,avatar,email,password,gender,age,intro,prefix,is_banned,email_verified,created_at,last_login,deleted_at FROM users ORDER BY created_at NULLS FIRST"
    )
    rows = []
    for r in src.fetchall():
        rows.append(
            (
                r[0], r[1], r[2] or "", r[3], r[4], r[5] or 0, map_age(r[6]),
                r[7] or "", r[8] or "", r[9] or 0, r[10] or 0,
                r[11], r[12], r[13],
            )
        )
    n = insert_many(
        dst,
        """INSERT INTO users
           (id,name,avatar,email,password,gender,age,intro,prefix,is_banned,email_verified,created_at,last_login,deleted_at)
           VALUES %s ON CONFLICT (id) DO NOTHING""",
        rows,
    )
    report.append(("users", len(rows), n))

    # ---------- posts ----------
    src.execute(
        "SELECT id,user_id,title,content,category,likes,views,status,created_at,updated_at FROM posts ORDER BY created_at NULLS FIRST"
    )
    rows = []
    for r in src.fetchall():
        created = r[8] or r[9]
        updated = r[9] or created
        if created is None:
            # 极端兜底：源行 created_at 为空时用当前时间，避免 published_at NOT NULL 失败
            from datetime import datetime, timezone
            created = updated = datetime.now(timezone.utc).replace(tzinfo=None)
        rows.append(
            (
                r[0], r[1], r[2], r[3], map_category(r[4]), r[5] or 0, r[6] or 0,
                r[7] if r[7] is not None else 1, created, updated,
                None, "markdown", created, True,
            )
        )
    n = insert_many(
        dst,
        """INSERT INTO posts
           (id,user_id,title,content,category,likes,views,status,created_at,updated_at,
            guild_id,content_format,published_at,publish_notified)
           VALUES %s ON CONFLICT (id) DO NOTHING""",
        rows,
    )
    report.append(("posts", len(rows), n))

    # ---------- comments（先不带 parent_id，避免自引用 FK 顺序问题）----------
    src.execute(
        "SELECT id,post_id,user_id,content,parent_id,likes,status,created_at FROM comments ORDER BY created_at NULLS FIRST"
    )
    rows = []
    parents = []
    for r in src.fetchall():
        rows.append((r[0], r[1], r[2], r[3], None, r[5] or 0, r[6] if r[6] is not None else 1, r[7], "markdown"))
        if r[4]:
            parents.append((r[0], r[4]))
    n = insert_many(
        dst,
        """INSERT INTO comments
           (id,post_id,user_id,content,parent_id,likes,status,created_at,content_format)
           VALUES %s ON CONFLICT (id) DO NOTHING""",
        rows,
    )
    if parents:
        extras.execute_values(
            dst,
            "UPDATE comments c SET parent_id = v.parent_id FROM (VALUES %s) AS v(id, parent_id) "
            "WHERE c.id = v.id AND EXISTS (SELECT 1 FROM comments p WHERE p.id = v.parent_id)",
            parents,
            page_size=PAGE,
        )
    report.append(("comments", len(rows), n))

    # ---------- 关系表 ----------
    rel = [
        ("post_likes", "post_id,user_id,created_at", "post_id,user_id,created_at", "(post_id,user_id)"),
        ("post_favorites", "post_id,user_id,created_at", "post_id,user_id,created_at", "(post_id,user_id)"),
        ("user_follows", "follower_id,following_id,created_at", "follower_id,following_id,created_at", "(follower_id,following_id)"),
        ("comment_likes", "comment_id,user_id,created_at", "comment_id,user_id,created_at", "(comment_id,user_id)"),
    ]
    for table, cols, target_cols, conflict in rel:
        src.execute(f"SELECT {cols} FROM {table}")
        rows = src.fetchall()
        n = insert_many(
            dst,
            f"INSERT INTO {table} ({target_cols}) VALUES %s ON CONFLICT {conflict} DO NOTHING",
            rows,
        )
        report.append((table, len(rows), n))

    # ---------- version_votes ----------
    src.execute("SELECT voter_key,voter_id,voter_name,choice,created_at,updated_at FROM version_votes")
    rows = src.fetchall()
    n = insert_many(
        dst,
        """INSERT INTO version_votes (voter_key,voter_id,voter_name,choice,created_at,updated_at)
           VALUES %s ON CONFLICT (voter_key) DO NOTHING""",
        rows,
    )
    report.append(("version_votes", len(rows), n))

    # ---------- bug_reports（无唯一键，按 title+created_at 去重）----------
    src.execute(
        "SELECT title,detail,steps,contact,reporter_id,reporter_name,user_agent,page_url,status,created_at FROM bug_reports ORDER BY created_at"
    )
    rows = src.fetchall()
    dst.execute("SELECT title, created_at FROM bug_reports")
    seen = {(r[0], r[1]) for r in dst.fetchall()}
    new_rows = [r for r in rows if (r[0], r[9]) not in seen]
    n = insert_many(
        dst,
        """INSERT INTO bug_reports
           (title,detail,steps,contact,reporter_id,reporter_name,user_agent,page_url,status,created_at)
           VALUES %s""",
        new_rows,
    )
    report.append(("bug_reports", len(rows), n))

    # ---------- world -> world_messages ----------
    src.execute("SELECT id,sender_id,sender_name,content,parent_id,created_at FROM world ORDER BY id")
    rows = []
    wparents = []
    for r in src.fetchall():
        rows.append((r[0], r[1], r[2] or "", "", r[3], "html", None, 1, r[5]))
        if r[4]:
            wparents.append((r[0], r[4]))
    n = insert_many(
        dst,
        """INSERT INTO world_messages
           (id,sender_id,sender_name,sender_avatar,content,content_format,parent_id,status,created_at)
           VALUES %s ON CONFLICT (id) DO NOTHING""",
        rows,
    )
    if wparents:
        extras.execute_values(
            dst,
            "UPDATE world_messages w SET parent_id = v.parent_id FROM (VALUES %s) AS v(id, parent_id) "
            "WHERE w.id = v.id AND EXISTS (SELECT 1 FROM world_messages p WHERE p.id = v.parent_id)",
            wparents,
            page_size=PAGE,
        )
    if rows:
        dst.execute(
            "SELECT setval(pg_get_serial_sequence('world_messages','id'), COALESCE((SELECT max(id) FROM world_messages),1), true)"
        )
    report.append(("world_messages", len(rows), n))

    # ---------- 站点公告（可选）----------
    src.execute("SELECT key, value FROM site_settings")
    settings = {k: v for k, v in src.fetchall()}
    enabled = str(settings.get("SITE_ANNOUNCEMENT_ENABLED", "0")).lower() in ("1", "true", "yes")
    text = settings.get("SITE_ANNOUNCEMENT_TEXT", "") or ""
    if enabled and text:
        payload = json.dumps({"enabled": True, "text": text, "version": 1, "updated_at": ""}, ensure_ascii=False)
        dst.execute(
            """INSERT INTO site_configs(key,value,updated_at) VALUES ('announcement', %s, now())
               ON CONFLICT (key) DO UPDATE SET value=EXCLUDED.value, updated_at=now()""",
            (payload,),
        )
        report.append(("site_configs.announcement", 1, 1))
    else:
        report.append(("site_configs.announcement", 0, 0))

    target.commit()
    return report


def main():
    ap = argparse.ArgumentParser(description="forum_user -> forum_user2 迁移")
    ap.add_argument("--source", default=os.getenv("SOURCE_DATABASE_URL"))
    ap.add_argument("--target", default=os.getenv("TARGET_DATABASE_URL"))
    ap.add_argument("--migrations-dir", default="server/internal/database/migrations")
    ap.add_argument("--create-db", action="store_true")
    ap.add_argument("--skip-schema", action="store_true")
    ap.add_argument("--apply", action="store_true", help="真正写入；不加则只做 dry-run")
    args = ap.parse_args()

    if not args.source or not args.target:
        sys.exit("请设置 SOURCE_DATABASE_URL 与 TARGET_DATABASE_URL（或 --source/--target）")

    print(f"[src] {args.source.split('@')[-1]}")
    print(f"[dst] {args.target.split('@')[-1]}")

    created = False
    if args.create_db:
        if not args.apply:
            print("[db] dry-run：将检查/创建目标库")
        else:
            created = ensure_database(args.target)

    source = conn(args.source)
    try:
        target = conn(args.target)
    except psycopg2.OperationalError as e:
        sys.exit(f"连接目标库失败（不存在？加 --create-db）：{e}")

    try:
        if not args.skip_schema:
            if args.apply:
                apply_migrations(target, args.migrations_dir)
            else:
                print("[schema] dry-run：跳过迁移，仅检查连接")

        if not args.apply:
            print("\n[dry-run] 源库行数：")
            with source.cursor() as c:
                for t in ("users", "posts", "comments", "world", "post_likes", "post_favorites",
                          "user_follows", "comment_likes", "bug_reports", "version_votes"):
                    c.execute(f"SELECT count(*) FROM {t}")
                    print(f"  {t:16s} {c.fetchone()[0]}")
            print("\n[dry-run] 未写入任何数据；确认后加 --apply")
            return

        report = run(source, target, args)
        print("\n===== 迁移结果 =====")
        print(f"{'表':24s} {'源行数':>8s} {'本次写入':>8s}")
        for name, total, inserted in report:
            print(f"{name:24s} {total:8d} {inserted:8d}")

        print("\n===== 目标库校验 =====")
        with target.cursor() as c:
            for t in ("users", "posts", "comments", "world_messages", "post_likes",
                      "post_favorites", "user_follows", "comment_likes", "bug_reports", "version_votes"):
                c.execute(f"SELECT count(*) FROM {t}")
                print(f"  {t:20s} {c.fetchone()[0]}")
            c.execute("SELECT version, dirty FROM schema_migrations LIMIT 1")
            print(f"  schema_migrations   {c.fetchone()}")
        print("\n完成。")
    finally:
        source.close()
        target.close()


if __name__ == "__main__":
    main()
