"""数据库访问层 — 连接管理 + 通用查询封装 + XSS 净化。

使用 psycopg2 简单 ThreadLocal 连接（每线程一个连接自动复用，用完不关闭，
进程退出时关闭池）。上层调用统一使用 execute_query / execute_insert。
"""
import atexit
import re
import threading
from contextlib import contextmanager
from typing import Any, Iterable

import psycopg2
from psycopg2.extras import RealDictCursor, RealDictRow

import config

_conn_local = threading.local()
_conn_lock = threading.Lock()


# ── XSS 净化：危险标签 / 事件属性 / 伪协议 ──────────────────
DANGEROUS_TAGS = {
    "script", "iframe", "embed", "object", "applet", "base", "form",
    "input", "textarea", "select", "option", "button", "link", "meta",
    "style", "svg", "math", "frame", "frameset", "video", "audio", "source",
}


def safe_html(content):
    """对用户提交的 HTML 内容进行基础净化（黑名单 + 事件属性移除）。"""
    if not content:
        return ""
    import html as html_module
    content = html_module.unescape(content)
    # 移除 HTML 注释（可藏恶意代码）
    content = re.sub(r"<!--[\s\S]*?-->", "", content)
    # 移除危险标签（开标签和自闭合）
    tag_pattern = "|".join(sorted(DANGEROUS_TAGS))
    content = re.sub(rf"<(?:{tag_pattern})\b[^>]*>", "", content, flags=re.IGNORECASE)
    content = re.sub(rf"</(?:{tag_pattern})\s*>", "", content, flags=re.IGNORECASE)
    # 移除所有事件处理属性 onXxx=...
    content = re.sub(r"\son\w+\s*=\s*(\"[^\"]*\"|'[^']*'|[^\s>]+)", "", content, flags=re.IGNORECASE)
    # 移除 javascript: 伪协议
    content = re.sub(
        r"(href|src|action|formaction)\s*=\s*(\"javascript:[^\"]*\"|'javascript:[^']*'|javascript:[^\s>]+)",
        "", content, flags=re.IGNORECASE,
    )
    # 移除 data:text/html 伪协议
    content = re.sub(
        r"(href|src|action)\s*=\s*(\"data:text/html[^\"]*\"|'data:text/html[^']*')",
        "", content, flags=re.IGNORECASE,
    )
    return content


def _get_conn():
    """获取当前线程连接（懒创建）。"""
    conn = getattr(_conn_local, "conn", None)
    if conn is None or conn.closed:
        if not config.database_url:
            raise RuntimeError("DATABASE_URL 未在 .env 中配置")
        with _conn_lock:
            conn = psycopg2.connect(config.database_url)
            conn.autocommit = False
        _conn_local.conn = conn
    return conn


@contextmanager
def _cursor(cursor_factory=RealDictCursor):
    """上下文管理器：获取游标，出错自动回滚，成功自动提交。"""
    conn = _get_conn()
    cur = conn.cursor(cursor_factory=cursor_factory)
    try:
        yield cur
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()


def close_pool():
    """进程退出时关闭所有线程连接（尽力而为）。"""
    with _conn_lock:
        conn = getattr(_conn_local, "conn", None)
        if conn and not conn.closed:
            try:
                conn.close()
            except Exception:
                pass
        _conn_local.conn = None


atexit.register(close_pool)


# ──────────────────────────────────────────────
# 对外通用查询封装
# ──────────────────────────────────────────────
def execute_query(query: str, params: Iterable[Any] | None = None,
                  fetch: bool = False, fetch_all: bool = False):
    """执行 SELECT / UPDATE / DELETE 等语句。

    Args:
        query:      SQL 语句（%s 占位）
        params:     参数元组 / 列表
        fetch:      返回 fetchone() 结果（一行 dict）
        fetch_all:  返回 fetchall() 结果（list[dict]）

    Returns:
        fetch=True → 单条 dict 或 None
        fetch_all=True → list[dict]
        否则 → 受影响行数（rowcount）
    """
    with _cursor() as cur:
        cur.execute(query, params or ())
        if fetch_all:
            rows = cur.fetchall()
            return [dict(r) if isinstance(r, RealDictRow) else r for r in rows]
        if fetch:
            r = cur.fetchone()
            return dict(r) if isinstance(r, RealDictRow) else r
        return cur.rowcount


def execute_insert(query: str, params: Iterable[Any] | None = None):
    """执行 INSERT 语句，返回 rowcount。"""
    with _cursor() as cur:
        cur.execute(query, params or ())
        return cur.rowcount


def init_database():
    """执行所有建表 SQL。"""
    if not config.database_url:
        raise RuntimeError("DATABASE_URL 未在 .env 中配置")
    with _cursor() as cur:
        for sql in config.ALL_TABLE_SQL:
            cur.execute(sql)
    print("[DB] 所有数据表 & 索引初始化完成")


# 子模块导入（供 db.* 外部访问）
from . import user  # noqa: E402  F401
from . import post  # noqa: E402  F401
from . import comment  # noqa: E402  F401
from . import world  # noqa: E402  F401
from . import search  # noqa: E402  F401
from . import follow  # noqa: E402  F401
from . import verify  # noqa: E402  F401
from . import bug  # noqa: E402  F401

__all__ = [
    "execute_query",
    "execute_insert",
    "init_database",
    "close_pool",
    "safe_html",
    "user",
    "post",
    "comment",
    "world",
    "search",
    "follow",
    "verify",
    "bug",
]
