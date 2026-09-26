# -*- coding: utf-8 -*-
"""登录凭证持久化：``~/.Cr/forum/account.bin``。

服务端认证仅靠两个 HttpOnly Cookie（``token`` / ``ID``），
原生客户端需要自己保存，否则每次启动都要重新登录。
文件内容用 :mod:`app.crypto` 封存（与机器指纹绑定），明文形式不落盘。
"""

from __future__ import annotations

import json
import os
import threading
import time
from pathlib import Path

from . import crypto, logger, paths

COOKIE_TOKEN = "token"
COOKIE_ID = "ID"
COOKIE_NAMES = (COOKIE_TOKEN, COOKIE_ID)

_log = logger.get_logger("session")


class SessionStore:
    """登录状态（Cookie + 用户快照）。"""

    def __init__(self, path: Path | None = None) -> None:
        self._path = Path(path) if path else paths.account_file()
        self._lock = threading.RLock()
        self._cookies: dict[str, str] = {}
        self._user: dict | None = None
        self._last_name = ""
        self._saved_at = 0.0
        self.load()

    # ── 读写 ──
    def load(self) -> None:
        with self._lock:
            self._cookies, self._user, self._last_name, self._saved_at = {}, None, "", 0.0
            if not self._path.is_file():
                return
            try:
                raw = crypto.unseal(self._path.read_bytes())
                payload = json.loads(raw.decode("utf-8"))
            except Exception as exc:
                _log.warning("凭证文件无法解密，已忽略：%s", exc)
                return
            if not isinstance(payload, dict):
                return
            cookies = payload.get("cookies") or {}
            if isinstance(cookies, dict):
                self._cookies = {k: str(v) for k, v in cookies.items()
                                 if k in COOKIE_NAMES and v}
            user = payload.get("user")
            self._user = user if isinstance(user, dict) else None
            self._last_name = str(payload.get("last_name") or "")
            self._saved_at = float(payload.get("saved_at") or 0.0)

    def save(self, cookies: dict | None = None, user: dict | None = None,
             *, last_name: str | None = None) -> bool:
        """写入凭证；传 None 表示保留当前值。"""
        with self._lock:
            if cookies is not None:
                self._cookies = {k: str(v) for k, v in cookies.items()
                                 if k in COOKIE_NAMES and v}
            if user is not None:
                self._user = user or None
            if last_name is not None:
                self._last_name = str(last_name)
            self._saved_at = time.time()
            payload = {
                "v": 1,
                "cookies": self._cookies,
                "user": self._user,
                "last_name": self._last_name,
                "saved_at": self._saved_at,
            }
            try:
                self._path.parent.mkdir(parents=True, exist_ok=True)
                blob = crypto.seal(
                    json.dumps(payload, ensure_ascii=False).encode("utf-8"))
                tmp = self._path.with_suffix(self._path.suffix + ".tmp")
                tmp.write_bytes(blob)
                os.replace(tmp, self._path)
                return True
            except Exception as exc:
                _log.error("凭证保存失败：%s", exc)
                return False

    def clear(self) -> None:
        """登出：清掉 Cookie，但保留最后一次登录的昵称以便预填。"""
        with self._lock:
            self._cookies = {}
            self._user = None
            self._saved_at = 0.0
            try:
                if self._path.is_file():
                    self._path.unlink()
            except OSError:
                pass

    # ── 访问 ──
    @property
    def cookies(self) -> dict[str, str]:
        with self._lock:
            return dict(self._cookies)

    @property
    def token(self) -> str:
        return self._cookies.get(COOKIE_TOKEN, "")

    @property
    def user_id(self) -> str:
        return self._cookies.get(COOKIE_ID, "")

    @property
    def user(self) -> dict | None:
        with self._lock:
            return dict(self._user) if self._user else None

    @property
    def last_name(self) -> str:
        return self._last_name

    @property
    def saved_at(self) -> float:
        return self._saved_at

    @property
    def has_credentials(self) -> bool:
        return bool(self.token and self.user_id)

    @property
    def is_expired(self) -> bool:
        """按服务端 7 天 TTL 估算是否可能过期（用于给用户提示）。"""
        if not self._saved_at:
            return True
        return (time.time() - self._saved_at) > 7 * 86400
