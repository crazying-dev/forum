# -*- coding: utf-8 -*-
"""LPK 解包底层工具（移植自 ``lpk2moc3/Core/utils.py``）。

与原实现的差异：

* 去掉一切界面/日志依赖，纯标准库 + 可选的 ``filetype``；
* ``filetype`` 缺失时退回内置「魔术字节」探测，保证最小依赖下也能解包；
* ``filetype.add_type(...)`` 包在 ``try/except`` 里，重复导入/重复调用不会抛异常；
* 额外带一个 ``normalize``（取自上游更新版），把角色名里的 Windows 非法字符去掉。

保留原实现的同名函数：``hashed_filename`` / ``safe_mkdir`` / ``genkey`` /
``decrypt`` / ``match_rule`` / ``is_encrypted_file`` / ``get_encrypted_file`` /
``travels_dict`` / ``travels_list`` / ``Moc3`` / ``Moc`` / ``guess_type``。
"""

from __future__ import annotations

import json
import os
import re
from hashlib import md5
from typing import Iterator

try:  # filetype 属于可选依赖：仓库依赖里有，缺失时也要能跑
    import filetype as _filetype  # type: ignore
    from filetype.types import Type as _FileType  # type: ignore
except Exception:  # pragma: no cover - 取决于运行环境
    _filetype = None

    class _FileType:  # type: ignore[no-redef]
        """``filetype.types.Type`` 的占位实现（未安装 filetype 时使用）。"""

        def __init__(self, mime: str = "", extension: str = "") -> None:
            self.mime = mime
            self.extension = extension


# ────────────────────────── 文件名 / 目录 ──────────────────────────


def hashed_filename(s: str) -> str:
    """LPK 内条目名：明文的 md5 十六进制串。"""
    t = md5()
    t.update(s.encode())
    return t.hexdigest()


def normalize(s: str) -> str:
    """净化文件名：去掉控制字符与 Windows 非法字符（取自上游更新版）。"""
    s = "".join(c for c in s if ord(c) >= 32 or c == " ")
    s = re.sub(r'[<>:"|?*]', "", s)
    if not s.strip():
        s = "unnamed"
    return s


def safe_mkdir(s: str) -> None:
    """已存在则忽略（原实现同名函数：只建一级目录）。"""
    try:
        os.mkdir(s)
    except FileExistsError:
        pass


# ────────────────────────── 加解密 ──────────────────────────


def genkey(s: str) -> int:
    """由密钥串算出解密 key（32 位折叠成有符号整数）。"""
    ret = 0
    for i in s:
        ret = (ret * 31 + ord(i)) & 0xffffffff
    if ret & 0x80000000:
        ret = ret | 0xffffffff00000000
    return ret


def decrypt(key: int, data: bytes) -> bytes:
    """LPK 的自定义流式解密：每 1024 字节切片重置一次 key。"""
    ret = []
    for chunk in [data[i:i + 1024] for i in range(0, len(data), 1024)]:
        tmpkey = key
        for i in chunk:
            tmpkey = (65535 & 2531011 + 214013 * tmpkey >> 16) & 0xffffffff
            ret.append((tmpkey & 0xff) ^ i)
    return bytes(ret)


# ────────────────────────── 条目名 → 是否加密文件 ──────────────────────────

match_rule = re.compile(r"^[0-9a-f]{32}.bin3?$")


def is_encrypted_file(s: str) -> bool:
    """形如 ``<md5>.bin`` / ``<md5>.bin3`` 的条目即加密资源。"""
    if match_rule.match(s) is not None:
        return True
    return False


def get_encrypted_file(s: str):
    """取出可能被 ``change_cos`` 前缀包裹的加密条目名；不是则返回 None。"""
    if not isinstance(s, str):
        return None
    if s.startswith("change_cos"):
        filename = s[len("change_cos "):]
    else:
        filename = s
    if not is_encrypted_file(filename):
        return None
    return filename


# ────────────────────────── 遍历 JSON ──────────────────────────


def travels_dict(dic: dict) -> Iterator[tuple[str, object]]:
    """深度优先遍历 dict，产出 ``(下划线拼接的路径, 叶子值)``。"""
    for k in dic:
        if type(dic[k]) == dict:
            for p, v in travels_dict(dic[k]):
                yield "%s_%s" % (k, p), v
        elif type(dic[k]) == list:
            for p, v in travels_list(dic[k]):
                yield "%s_%s" % (k, p), v
        else:
            yield str(k), dic[k]


def travels_list(vals: list) -> Iterator[tuple[str, object]]:
    """深度优先遍历 list，产出 ``(下划线拼接的路径, 叶子值)``。"""
    for i in range(len(vals)):
        if type(vals[i]) == dict:
            for p, v in travels_dict(vals[i]):
                yield "%s_%s" % (i, p), v
        elif type(vals[i]) == list:
            for p, v in travels_list(vals[i]):
                yield "%s_%s" % (i, p), v
        else:
            yield str(i), vals[i]


# ────────────────────────── 文件类型识别 ──────────────────────────


class Moc3(_FileType):
    """Live2D Cubism 3+ 的 ``.moc3``。"""

    MIME = "application/moc3"
    EXTENSION = "moc3"

    def __init__(self) -> None:
        super(Moc3, self).__init__(mime=Moc3.MIME, extension=Moc3.EXTENSION)

    def match(self, buf: bytes) -> bool:
        return len(buf) > 3 and buf.startswith(b"MOC3")


class Moc(_FileType):
    """Live2D Cubism 2 的 ``.moc``。"""

    MIME = "application/moc"
    EXTENSION = "moc"

    def __init__(self) -> None:
        super(Moc, self).__init__(mime=Moc.MIME, extension=Moc.EXTENSION)

    def match(self, buf: bytes) -> bool:
        return len(buf) > 3 and buf.startswith(b"moc")


def _register_types() -> None:
    """把 Moc3/Moc 注册进 ``filetype``；重复导入时忽略重复注册。"""
    if _filetype is None:
        return
    for ftype in (Moc3(), Moc()):
        try:
            _filetype.add_type(ftype)
        except Exception:
            # 同一个模块被 reload / 多个入口导入时会重复注册，忽略即可
            pass


_register_types()

#: 内置探测表（filetype 缺失或没识别出来时兜底）
_MAGIC_EXTENSIONS: tuple[tuple[bytes, str], ...] = (
    (b"\x89PNG\r\n\x1a\n", ".png"),
    (b"\xff\xd8\xff", ".jpg"),
    (b"GIF87a", ".gif"),
    (b"GIF89a", ".gif"),
    (b"BM", ".bmp"),
    (b"OggS", ".ogg"),
    (b"ID3", ".mp3"),
    (b"%PDF", ".pdf"),
    (b"PK\x03\x04", ".zip"),
    (b"MOC3", ".moc3"),
    (b"moc", ".moc"),
)


def _sniff_extension(data: bytes) -> str:
    """最小化的魔术字节探测（只覆盖 LPK 里常见的几种）。"""
    if len(data) >= 12 and data.startswith(b"RIFF"):
        return ".webp" if data[8:12] == b"WEBP" else ".wav"
    for magic, ext in _MAGIC_EXTENSIONS:
        if data.startswith(magic):
            return ext
    return ""


def guess_type(data: bytes) -> str:
    """猜扩展名（含点）：filetype → 内置魔术字节 → 能否当 JSON 解析 → ""。"""
    if _filetype is not None:
        try:
            ftype = _filetype.guess(data)
        except Exception:
            ftype = None
        if ftype is not None:
            return "." + ftype.extension
    ext = _sniff_extension(data)
    if ext:
        return ext
    try:
        json.loads(data.decode("utf8"))
        return ".json"
    except Exception:
        return ""
