# -*- coding: utf-8 -*-
"""深链处理：``Crforum://`` 的解析与注册表登记（HKCU，无需管理员）。

支持的深链：

* ``Crforum://home`` / ``forum`` / ``world`` / ``settings`` / ``me``
* ``Crforum://post/<post_id>``、``Crforum://user/<user_id>``
* ``Crforum://wiki?kind=overview|official|personal|mouse|mouse_linux|live2d``
* ``Crforum://search?k=关键词``
* ``Crforum://auth?mode=login|register|reset``
* ``Crforum://open?to=<站内地址>``
"""

from __future__ import annotations

import sys
from urllib.parse import parse_qs, unquote, urlparse

from . import constants, logger

_log = logger.get_logger("deeplink")

SCHEME_KEY = "Software\\Classes\\" + constants.URI_SCHEME

VALID_ROUTES = {
    "home", "forum", "world", "wiki", "settings", "me", "auth",
    "search", "post", "user", "open", "privacy", "huiguan", "easter_egg",
}

WIKI_KINDS = {"overview", "official", "personal", "mouse", "mouse_linux", "live2d"}


# ────────────────────────── 解析 ──────────────────────────


def route_from_url(url: str) -> tuple[str, dict]:
    """``Crforum://post/PS123?x=1`` → ``('post', {'post_id': 'PS123'})``。"""
    raw = str(url or "").strip()
    if not raw:
        return "", {}
    if not raw.lower().startswith(constants.URI_SCHEME.lower() + "://"):
        return "", {}
    parsed = urlparse(raw)
    head = (parsed.netloc or "").strip().lower()
    tail = unquote((parsed.path or "").lstrip("/")).strip()
    query = {k: v[0] for k, v in parse_qs(parsed.query).items() if v}
    if not head and tail:
        parts = tail.split("/", 1)
        head = parts[0].lower()
        tail = parts[1] if len(parts) > 1 else ""
    if head not in VALID_ROUTES:
        return "", {}
    if head == "post":
        if not tail:
            return "forum", {}
        return "post", {"post_id": tail}
    if head == "user":
        if not tail:
            return "home", {}
        return "user", {"user_id": tail}
    if head == "wiki":
        kind = str(query.get("kind") or "overview").strip().lower()
        if kind not in WIKI_KINDS:
            kind = "overview"
        return "wiki", {"kind": kind}
    if head == "search":
        return "search", {"keyword": str(query.get("k") or "").strip()}
    if head == "auth":
        mode = str(query.get("mode") or "login").strip().lower()
        if mode not in ("login", "register", "reset"):
            mode = "login"
        return "auth", {"mode": mode}
    if head == "open":
        target = str(query.get("to") or "").strip()
        return ("open", {"url": target}) if target else ("home", {})
    if head == "easter_egg":
        return "easter_egg", {"play": True}
    return head, {}


def extract_urls(argv: list[str] | None = None) -> list[str]:
    """从命令行中挑出深链（Windows 会以 ``"Crforum://..."`` 形式传入）。"""
    args = list(sys.argv if argv is None else argv)
    out: list[str] = []
    prefix = constants.URI_SCHEME.lower() + "://"
    for item in args[1:]:
        text = str(item).strip().strip('"')
        if text.lower().startswith(prefix):
            out.append(text)
    return out


# ────────────────────────── 注册表 ──────────────────────────


def executable_path() -> str:
    """当前可执行文件（开发态返回 python.exe）。"""
    if getattr(sys, "frozen", False):
        return sys.executable
    return sys.executable


def _command_line(exe: str) -> str:
    if getattr(sys, "frozen", False):
        return '"%s" "%%1"' % exe
    script = sys.argv[0] if sys.argv else "main.py"
    return '"%s" "%s" "%%1"' % (exe, script)


def register_scheme(exe: str | None = None) -> tuple[bool, str]:
    """把 Crforum:// 关联到本程序（写 HKCU，无需 UAC）。"""
    try:
        import winreg
    except ImportError:
        return False, "当前系统不支持注册表操作"
    exe = exe or executable_path()
    try:
        with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, SCHEME_KEY, 0,
                                winreg.KEY_WRITE) as key:
            winreg.SetValueEx(key, "", 0, winreg.REG_SZ,
                              "URL:%s 协议" % constants.APP_NAME)
            winreg.SetValueEx(key, "URL Protocol", 0, winreg.REG_SZ, "")
            winreg.SetValueEx(key, "FriendlyTypeName", 0, winreg.REG_SZ,
                              "%s 客户端" % constants.APP_NAME)
        with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER,
                                SCHEME_KEY + "\\DefaultIcon", 0,
                                winreg.KEY_WRITE) as key:
            winreg.SetValueEx(key, "", 0, winreg.REG_SZ, "%s,0" % exe)
        with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER,
                                SCHEME_KEY + "\\shell\\open\\command", 0,
                                winreg.KEY_WRITE) as key:
            winreg.SetValueEx(key, "", 0, winreg.REG_SZ, _command_line(exe))
        _log.info("已注册深链协议 %s", constants.URI_SCHEME_DISPLAY)
        return True, "已启用 %s 链接" % constants.URI_SCHEME_DISPLAY
    except OSError as exc:
        _log.error("注册深链失败：%s", exc)
        return False, "注册失败：%s" % exc


def unregister_scheme() -> tuple[bool, str]:
    try:
        import winreg
        winreg.DeleteKey(winreg.HKEY_CURRENT_USER, SCHEME_KEY + "\\shell\\open\\command")
        winreg.DeleteKey(winreg.HKEY_CURRENT_USER, SCHEME_KEY + "\\shell\\open")
        winreg.DeleteKey(winreg.HKEY_CURRENT_USER, SCHEME_KEY + "\\shell")
        winreg.DeleteKey(winreg.HKEY_CURRENT_USER, SCHEME_KEY + "\\DefaultIcon")
        winreg.DeleteKey(winreg.HKEY_CURRENT_USER, SCHEME_KEY)
        return True, "已取消 %s 链接关联" % constants.URI_SCHEME_DISPLAY
    except FileNotFoundError:
        return True, "本就没有关联"
    except OSError as exc:
        return False, "删除失败：%s" % exc


def is_registered() -> bool:
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                            SCHEME_KEY + "\\shell\\open\\command") as key:
            value, _ = winreg.QueryValueEx(key, "")
        return bool(value)
    except OSError:
        return False
