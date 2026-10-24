"""轻量内存限流：按 (IP, action) 在窗口期内限制请求次数（线程安全）。

用法：
    if rate_limit('login', 10, 300):
        return jsonify({'success': False, 'message': '请求过于频繁，请5分钟后再试'}), 429
"""
from __future__ import annotations

import threading
import time

from flask import request

_lock = threading.Lock()
_records: dict = {}


def _client_ip() -> str:
    forwarded = request.headers.get("X-Forwarded-For", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.remote_addr or "0.0.0.0"


def rate_limit(action: str, max_requests: int, window_seconds: int) -> bool:
    """窗口期内超过 max_requests 次返回 True（调用方应拒绝请求）。"""
    key = (_client_ip(), action)
    now = time.time()
    with _lock:
        rec = _records.get(key)
        if not rec or now - rec["start"] >= window_seconds:
            # 新窗口
            _records[key] = {"start": now, "count": 1}
            return False
        rec["count"] += 1
        if rec["count"] > max_requests:
            return True
        return False
