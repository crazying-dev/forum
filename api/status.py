# -*- coding: utf-8 -*-
"""状态码日志 + 查询接口。

记录每次 HTTP 响应的「时间 + 状态码」，按 2xx / 4xx / 5xx 归类（1xx / 3xx 不入库）；
落盘为追加式文本文件（每行一个 JSON，只有 ``time`` 与 ``status``），仅保留最近 ``STATUS_LOG_MAX`` 条。

- 写入：由 app.py 的 after_request 钩子调用 :func:`record`
- 读取：``GET /api/status-log``（公开、无鉴权、无参数），返回全部明细（最新在前）
"""
from __future__ import annotations

import json
import os
import threading
from datetime import datetime

from flask import Blueprint, jsonify

import config

status_bp = Blueprint("status", __name__)

# 只记录这三类（1xx 信息 / 3xx 重定向不入库）
_TRACKED = ("2xx", "4xx", "5xx")

_LOCK = threading.Lock()

_DEFAULT_MAX = 10000


def _max_entries() -> int:
    try:
        n = int(getattr(config, "STATUS_LOG_MAX", _DEFAULT_MAX))
    except (TypeError, ValueError):
        n = _DEFAULT_MAX
    return n if n > 0 else _DEFAULT_MAX


def _path() -> str:
    return str(getattr(config, "STATUS_LOG_PATH", "") or "")


def status_class(code) -> str:
    """把状态码映射到 2xx / 4xx / 5xx 等类别（非法输入返回空串）。"""
    try:
        code = int(code)
    except (TypeError, ValueError):
        return ""
    if code < 100 or code > 599:
        return ""
    return "%dxx" % (code // 100)


def _now() -> str:
    """本地时间（带时区偏移），形如 2026-10-02T07:30:00+08:00。"""
    return datetime.now().astimezone().isoformat(timespec="seconds")


def record(status_code) -> None:
    """记录一次响应；仅当状态码属于 2xx / 4xx / 5xx 时写入（只存时间 + 状态码）。"""
    cls = status_class(status_code)
    if cls not in _TRACKED:
        return
    path = _path()
    if not path:
        return
    entry = {"time": _now(), "status": int(status_code)}
    line = json.dumps(entry, ensure_ascii=False)
    with _LOCK:
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
        except OSError:
            pass
        try:
            with open(path, "a", encoding="utf-8") as f:
                f.write(line + "\n")
        except OSError:
            return
        _trim(path)


def _trim(path: str) -> None:
    """文件超过上限时只保留最新 N 行（调用方需已持有 _LOCK）。"""
    limit = _max_entries()
    try:
        with open(path, "r", encoding="utf-8") as f:
            lines = f.readlines()
    except OSError:
        return
    if len(lines) <= limit:
        return
    try:
        with open(path, "w", encoding="utf-8") as f:
            f.writelines(lines[-limit:])
    except OSError:
        pass


def recent() -> list:
    """返回全部已记录的明细（按时间倒序，最新的在最前）。"""
    path = _path()
    if not path or not os.path.isfile(path):
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            lines = f.readlines()
    except OSError:
        return []
    out: list = []
    for raw in reversed(lines):
        raw = raw.strip()
        if not raw:
            continue
        try:
            out.append(json.loads(raw))
        except ValueError:
            continue
    return out


@status_bp.route("/status-log", methods=["GET"])
def status_log_api():
    """状态码日志明细（2xx / 4xx / 5xx 的发生时间）；无参数，返回全部（最新在前）。"""
    entries = recent()
    return jsonify({
        "success": True,
        "count": len(entries),
        "entries": entries,
    })
