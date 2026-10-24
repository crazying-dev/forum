"""世界频道增量轮询（GET /api/world/ALL?since=...）契约测试。

覆盖：
  1. db.world.get_world_messages 传入 since 时加 `created_at > %s` 过滤，且 since 走参数绑定；
  2. 不传 since 时保持全量（无 WHERE 过滤）；
  3. 路由解析 since 并透传；空 / 非法 since 回落为全量；
  4. 返回体仍是裸数组、响应头不变（向后兼容）。

均不依赖数据库：db 层用 monkeypatch，路由用 test_request_context。
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest
from flask import Flask

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import db.world as world_db          # noqa: E402
import api.world as world_api        # noqa: E402


class _Capture:
    """替身 execute_query：记录入参并回放给定行。"""

    def __init__(self, rows=None):
        self.calls = []
        self.rows = rows or []

    def __call__(self, sql, params=None, fetch_all=False, fetch=False, **kw):
        self.calls.append((sql, params))
        if fetch_all:
            return list(self.rows)
        return None


# ────────────────────── db 层 ──────────────────────


def test_db_applies_strict_since_filter(monkeypatch):
    """传入 since 时必须使用严格大于（`created_at > %s`），否则会重复回带旧消息。"""
    row = {"id": 2, "sender_id": "u", "sender_name": "n", "content": "c",
           "parent_id": None, "created_at": "2026-05-06 12:00:01", "sender_avatar": None}
    cap = _Capture([row])
    monkeypatch.setattr(world_db, "execute_query", cap)

    out = world_db.get_world_messages(since="2026-05-06 12:00:00")

    sql, params = cap.calls[0]
    assert "created_at > %s" in sql, "since 未以严格大于过滤"
    assert params[0] == "2026-05-06 12:00:00", "since 未作为第一个参数绑定"
    assert params[-1] == 100, "limit 仍应作为最后一个参数"
    assert "ORDER BY w.created_at DESC" in sql, "排序口径不得变更"
    assert out and out[0]["id"] == 2


def test_db_without_since_is_full_list(monkeypatch):
    """不传 since 时保持全量（无 WHERE），向后兼容旧客户端。"""
    cap = _Capture([])
    monkeypatch.setattr(world_db, "execute_query", cap)

    world_db.get_world_messages()

    sql, params = cap.calls[0]
    assert "WHERE" not in sql.upper(), "无 since 时不应出现 WHERE 过滤"
    assert params == (100,)


def test_db_custom_limit(monkeypatch):
    cap = _Capture([])
    monkeypatch.setattr(world_db, "execute_query", cap)
    world_db.get_world_messages(limit=50, since="2026-05-06 12:00:00")
    _, params = cap.calls[0]
    assert params[-1] == 50


# ────────────────────── 路由层 ──────────────────────


def _client():
    app = Flask(__name__)
    app.register_blueprint(world_api.world_bp, url_prefix="/api/world")
    return app.test_client()


def _capture_route(monkeypatch):
    seen = {}

    def fake_get(limit=100, since=None):
        seen["since"] = since
        return []

    monkeypatch.setattr(world_api.db.world, "get_world_messages", fake_get)
    return seen


def test_route_passes_since_through(monkeypatch):
    seen = _capture_route(monkeypatch)
    r = _client().get("/api/world/ALL?since=2026-05-06%2012:00:00")
    assert r.status_code == 200
    assert seen["since"] == "2026-05-06 12:00:00"
    assert r.get_json() == [], "返回体必须是裸数组"
    assert r.headers.get("Cache-Control") == "max-age=2"


def test_route_without_since_is_none(monkeypatch):
    seen = _capture_route(monkeypatch)
    _client().get("/api/world/ALL")
    assert seen["since"] is None


@pytest.mark.parametrize("raw", ["", "   ", "hello", "2026/05/06",
                                 "2026-05-06 12:00:00; DROP TABLE world"])
def test_route_ignores_invalid_since(monkeypatch, raw):
    """非法 since 不得报错，而是回落为全量（避免数据库类型转换 500）。"""
    seen = _capture_route(monkeypatch)
    r = _client().get("/api/world/ALL", query_string={"since": raw})
    assert r.status_code == 200
    assert seen["since"] is None


@pytest.mark.parametrize("raw,expect", [
    ("2026-05-06", "2026-05-06"),
    ("2026-05-06 12:00", "2026-05-06 12:00"),
    ("2026-05-06 12:00:00", "2026-05-06 12:00:00"),
    ("2026-05-06 12:00:00.123456", "2026-05-06 12:00:00.123456"),
    ("2026-05-06T12:00:00Z", "2026-05-06T12:00:00Z"),
    ("2026-05-06T12:00:00+08:00", "2026-05-06T12:00:00+08:00"),
    ("  2026-05-06  ", "2026-05-06"),
    (None, None),
    ("", None),
    ("not-a-time", None),
])
def test_parse_since(raw, expect):
    assert world_api._parse_since(raw) == expect
