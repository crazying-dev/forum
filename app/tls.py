# -*- coding: utf-8 -*-
"""HTTPS 根证书解析（解决打包后 “安全连接失败”）。

背景：PyInstaller 的 ``hook-certifi`` 收集的是 ``certifi`` **包目录**里的
``cacert.pem``；而这台机器上该文件是一份**陈旧残留**（119 张证书 / 236 KB），
真正生效的是 ``certifi.where()`` 指向的另一份（190 张证书 / 354 KB）。
由于打包后写的仍是包目录里那份旧文件，所有 HTTPS 请求都会报
``CERTIFICATE_VERIFY_FAILED: unable to get local issuer certificate``。

对策：随包内置一份可信证书（``resources/ca/cacert.pem``），并在启动时：

1. 按优先级选一份可用的根证书文件（内置 → ``certifi.where()`` → certifi 包目录）；
2. 把它写进 ``REQUESTS_CA_BUNDLE`` / ``CURL_CA_BUNDLE`` / ``SSL_CERT_FILE``，
   让 ``requests``、标准库 ``ssl`` 等所有走环境变量的实现都统一使用它；
3. 供 :class:`app.api.ForumApi` 显式设置 ``session.verify``。

这样即使运行环境里 certifi 的证书包有问题，客户端仍能正常联网。
"""

from __future__ import annotations

import os
from pathlib import Path

from . import constants, logger

_log = logger.get_logger("tls")

#: 小于这个体积基本可以断定不是一份完整的根证书包
MIN_BUNDLE_BYTES = 100 * 1024

_ENV_NAMES = ("REQUESTS_CA_BUNDLE", "CURL_CA_BUNDLE", "SSL_CERT_FILE")

_resolved: str | None | bool = None   # None=未解析；False=未找到；str=已找到
_installed = False


def _is_sane(path) -> bool:
    """文件存在且体积合理（避免把残缺/空文件当成证书包）。"""
    if not path:
        return False
    try:
        p = Path(path)
        return p.is_file() and p.stat().st_size >= MIN_BUNDLE_BYTES
    except OSError:
        return False


def candidates() -> list[str]:
    """按优先级返回候选根证书路径（只做拼路径，不检查存在性）。"""
    out: list[str] = []
    try:
        out.append(str(constants.RES_CA_BUNDLE))
    except Exception:  # noqa: BLE001
        pass
    try:
        import certifi
        out.append(str(certifi.where()))
        out.append(os.path.join(os.path.dirname(certifi.__file__), "cacert.pem"))
    except Exception:  # noqa: BLE001
        pass
    return out


def bundle_path() -> str | None:
    """返回一份可用的根证书文件路径；找不到时返回 ``None``。"""
    global _resolved
    if _resolved is not None:
        return _resolved or None
    for candidate in candidates():
        if _is_sane(candidate):
            _resolved = candidate
            return candidate
    _resolved = False
    return None


def install() -> str:
    """选好根证书并写入环境变量（幂等，进程内只做一次）。返回路径或空串。"""
    global _installed
    if _installed:
        return str(bundle_path() or "")
    _installed = True
    path = bundle_path()
    if not path:
        _log.warning("未找到可用的根证书包，将退回系统/库默认校验")
        return ""
    for name in _ENV_NAMES:
        if not os.environ.get(name):
            os.environ[name] = path
    _log.info("HTTPS 根证书：%s", path)
    return path


def verify_target():
    """给 ``requests.Session.verify`` 用的值（路径字符串；无则 ``True``）。"""
    return bundle_path() or True
