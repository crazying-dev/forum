# -*- coding: utf-8 -*-
"""GitHub 访问回退：DoH 解析真实 IP、公共加速镜像、服务器反代地址。

下载 GitHub 上的更新包时按「直连 → DoH 修复 DNS → 公共加速 → 服务器反代」
逐级回退；只在“连接失败 / 超时”时升级，不因速度慢而降级。

* DoH 只接管 GitHub 相关域名的解析，其它域名（如 yjlt.top）行为完全不变
* 公共加速与服务器反代只是把原始 URL 拼一个前缀；下载后统一校验 sha256，
  镜像即便被篡改也会被直接拒绝
"""
from __future__ import annotations

import socket
import threading
import time
from urllib.parse import urlparse

import requests

from . import constants, logger

_log = logger.get_logger("netfallback")

DOH_TIMEOUT = 3.0      # 单个 DoH 查询超时（秒）
DOH_TTL = 300.0        # DNS 结果缓存时间（秒）

# GitHub 相关域名（含 Release 资源实际落地的 CDN 域名）
GITHUB_SUFFIXES = ("github.com", "githubusercontent.com", "githubassets.com",
                   "github.io", "ghcr.io")


def is_github_host(host: str) -> bool:
    """域名是否属于 GitHub（含 Release 资源的 CDN 域名）。"""
    text = str(host or "").strip().lower().rstrip(".")
    if not text:
        return False
    return any(text == suffix or text.endswith("." + suffix)
               for suffix in GITHUB_SUFFIXES)


def is_github_url(url: str) -> bool:
    """URL 是否指向 GitHub（解析失败一律当作非 GitHub）。"""
    try:
        return is_github_host(urlparse(str(url or "")).hostname or "")
    except Exception:  # noqa: BLE001
        return False


# ────────────────────── DoH 解析 ──────────────────────

_cache: dict = {}
_cache_lock = threading.Lock()


def _cache_get(host: str):
    with _cache_lock:
        item = _cache.get(host)
    if not item:
        return None
    ips, stamp = item
    if time.time() - stamp > DOH_TTL:
        return None
    return list(ips)


def _cache_put(host: str, ips) -> None:
    with _cache_lock:
        _cache[host] = (list(ips), time.time())


def clear_cache() -> None:
    """清空 DoH 结果缓存（测试用）。"""
    with _cache_lock:
        _cache.clear()


def _parse_doh(payload) -> list:
    """DoH JSON（application/dns-json）→ IPv4 列表。"""
    ips: list = []
    if not isinstance(payload, dict):
        return ips
    answers = payload.get("Answer")
    if not isinstance(answers, list):
        return ips
    for item in answers:
        if not isinstance(item, dict):
            continue
        try:
            kind = int(item.get("type", 0))
        except (TypeError, ValueError):
            continue
        if kind != 1:            # 1 = A 记录
            continue
        data = str(item.get("data") or "").strip()
        if data:
            ips.append(data)
    return ips


def resolve(host: str) -> list:
    """按顺序尝试各 DoH 服务解析 IPv4；全部失败返回 ``[]``。"""
    host = str(host or "").strip().rstrip(".")
    if not host:
        return []
    cached = _cache_get(host)
    if cached:
        return cached
    params = {"name": host, "type": "A"}
    headers = {"accept": "application/dns-json", "User-Agent": constants.CLIENT_UA}
    for endpoint in constants.DOH_ENDPOINTS:
        try:
            resp = requests.get(endpoint, params=params, headers=headers,
                                timeout=DOH_TIMEOUT)
            try:
                if resp.status_code != 200:
                    continue
                ips = _parse_doh(resp.json())
            finally:
                resp.close()
        except Exception as exc:  # noqa: BLE001
            _log.debug("DoH 解析失败（%s）：%s", endpoint, exc)
            continue
        if ips:
            _log.info("DoH 解析 %s → %s", host, ", ".join(ips))
            _cache_put(host, ips)
            return ips
    _log.info("所有 DoH 服务都未能解析 %s", host)
    return []


# ────────────────────── socket 解析接管 ──────────────────────

_real_getaddrinfo = socket.getaddrinfo
_patch_lock = threading.Lock()
_patch_depth = 0


def _doh_getaddrinfo(host, port, family=0, type=0, proto=0, flags=0):
    """接管版 getaddrinfo：GitHub 域名先用 DoH 解析出的 IP，其余原样处理。"""
    name = host
    if isinstance(host, bytes):
        try:
            name = host.decode("ascii", "ignore")
        except Exception:  # noqa: BLE001
            name = host
    if isinstance(name, str) and is_github_host(name):
        for ip in resolve(name):
            try:
                return _real_getaddrinfo(ip, port, family, type, proto, flags)
            except Exception:  # noqa: BLE001
                continue
        _log.info("DoH 未给出 %s 地址，回退系统解析", name)
    return _real_getaddrinfo(host, port, family, type, proto, flags)


def _install_patch() -> None:
    global _patch_depth
    with _patch_lock:
        if _patch_depth == 0:
            socket.getaddrinfo = _doh_getaddrinfo
        _patch_depth += 1


def _release_patch() -> None:
    global _patch_depth
    with _patch_lock:
        _patch_depth = max(0, _patch_depth - 1)
        if _patch_depth == 0:
            socket.getaddrinfo = _real_getaddrinfo


class doh_dns:
    """上下文管理器：在作用域内用 DoH 结果接管 GitHub 域名的解析。"""

    def __enter__(self):
        _install_patch()
        return self

    def __exit__(self, *exc):
        _release_patch()
        return False


def patched() -> bool:
    """当前是否已接管解析（测试用）。"""
    return socket.getaddrinfo is _doh_getaddrinfo


# ────────────────────── 加速 / 反代地址 ──────────────────────


def accelerate(url: str) -> list:
    """公共加速候选（ghproxy 风格：镜像前缀 + 原始 URL）。"""
    text = str(url or "").strip()
    if not text:
        return []
    return [str(base).rstrip("/") + "/" + text
            for base in constants.ACCELERATOR_MIRRORS if str(base or "").strip()]


def asset_basename(url: str) -> str:
    """URL 路径末段（GitHub 直链 → ``forum_setup.exe``）。"""
    try:
        return str(urlparse(str(url or "")).path).rsplit("/", 1)[-1].strip()
    except Exception:  # noqa: BLE001
        return ""


def server_mirror(url: str, filename: str = "") -> str:
    """服务器反代地址：``/api/app/mirror/<平台>/<文件名>``。"""
    name = str(filename or "").strip() or asset_basename(url)
    if not name:
        return ""
    try:
        return constants.api("/api/app/mirror/windows/%s" % name)
    except Exception as exc:  # noqa: BLE001
        _log.debug("服务器反代地址构建失败：%s", exc)
        return ""


def download_attempts(url: str, filename: str = "") -> list:
    """构造下载回退列表 → ``[(标签, 地址, 是否用 DoH), ...]``。

    非 GitHub 地址不生成任何回退（直连本身就是最终源）。
    """
    text = str(url or "").strip()
    if not text:
        return []
    if not is_github_url(text):
        return [("直连", text, False)]
    attempts = [("直连", text, False), ("DoH 修复", text, True)]
    for candidate in accelerate(text):
        host = urlparse(candidate).hostname or "镜像"
        attempts.append(("公共加速（%s）" % host, candidate, False))
    mirror = server_mirror(text, filename)
    if mirror:
        attempts.append(("服务器反代", mirror, False))
    return attempts
