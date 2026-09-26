# -*- coding: utf-8 -*-
"""通用小工具：HTML 转义 / 外链判定 / 字节格式化 / 系统打开。"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from html import escape as _escape
from urllib.parse import urlparse

_HASH_ONLY = re.compile(r"^#[^/]*$")
_SAFE_SCHEMES = ("http", "https")


def html_escape(text) -> str:
    """转义 HTML 特殊字符（用于少量富文本标签）。"""
    return _escape("" if text is None else str(text), quote=True)


def plain(text) -> str:
    """去掉 HTML 标签的纯文本。"""
    return re.sub(r"<[^>]+>", "", "" if text is None else str(text))


_HTTPS_HOSTS = ("www.yjlt.top", "yjlt.top")


def is_external_link(href: str | None) -> bool:
    """判断链接是否属于外部站（对照 AfterBody._isExternalLink）。"""
    if not href:
        return False
    s = str(href).strip()
    if not s or s.startswith(("#", "mailto:", "javascript:")):
        return False
    if s.startswith("//"):
        return True
    parsed = urlparse(s)
    if not parsed.scheme:
        return False
    if parsed.scheme not in _SAFE_SCHEMES:
        return False
    host = (parsed.netloc or "").lower().split(":")[0]
    if not host:
        return True
    return host not in _HTTPS_HOSTS and not host.endswith(".yjlt.top")


def human_size(num_bytes: int) -> str:
    """字节数 → 易读字符串。"""
    try:
        n = float(num_bytes)
    except (TypeError, ValueError):
        return "-"
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return ("%d %s" % (n, unit)) if unit == "B" else ("%.1f %s" % (n, unit))
        n /= 1024.0
    return "%.1f GB" % n


def safe_filename(name: str, fallback: str = "file") -> str:
    """把任意字符串变成可用作文件名的形式。"""
    s = re.sub(r'[\\/:*?"<>|\r\n\t]+', "_", str(name or "")).strip(" ._")
    return s or fallback


def open_in_system(target: str) -> bool:
    """用系统默认程序/浏览器打开路径或 URL。"""
    if not target:
        return False
    try:
        if sys.platform.startswith("win"):
            os.startfile(target)  # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            subprocess.Popen(["open", target])
        else:
            subprocess.Popen(["xdg-open", target])
        return True
    except Exception:
        return False


def reveal_in_explorer(path: str) -> bool:
    """在资源管理器中定位文件（Windows）。"""
    if not path:
        return False
    try:
        if sys.platform.startswith("win"):
            if os.path.isfile(path):
                subprocess.Popen(["explorer", "/select,", os.path.normpath(path)])
            else:
                os.startfile(os.path.normpath(path))  # type: ignore[attr-defined]
            return True
        return open_in_system(path)
    except Exception:
        return False
