# -*- coding: utf-8 -*-
"""客户端发布信息（「下载」页与更新检查共用）。

* 数据源：服务端 ``GET /api/app/releases``（见 :data:`app.constants.APP_RELEASES_API`）
* 远端不可达时回退到内置的 :data:`_fallback_platforms`，并把 ``known`` 记为 False
* 带 TTL 缓存 + 线程锁；对外函数都不抛异常
* ``known`` / ``source`` 用于区分「真实清单」与「离线兜底」，供更新检查判定
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Any

from . import api as api_mod
from . import constants, logger, util

_log = logger.get_logger("releases")

CACHE_TTL = 600            # 清单缓存有效期（秒）
STATUS_AVAILABLE = "available"
STATUS_COMING_SOON = "coming_soon"

PLATFORM_ORDER = ("windows", "android", "linux", "macos")
PLATFORM_LABELS = {
    "windows": "Windows",
    "android": "Android",
    "linux": "Linux",
    "macos": "macOS",
}
PLATFORM_ICONS = {
    "windows": "🪟",
    "android": "🤖",
    "linux": "🐧",
    "macos": "🍎",
}


def platform_label(key: str) -> str:
    return PLATFORM_LABELS.get(str(key), str(key).title())


def platform_icon(key: str) -> str:
    return PLATFORM_ICONS.get(str(key), "💾")


def _text(value) -> str:
    return str(value).strip() if value is not None else ""


def _int(value) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _notes(value) -> str:
    """更新说明：兼容字符串与列表（服务端 app_releases.json 用的是列表）。"""
    if value is None:
        return ""
    if isinstance(value, (list, tuple)):
        return "\n".join(str(item).strip() for item in value if str(item).strip())
    return str(value).strip()


def _norm_status(value) -> str:
    text = _text(value).lower().replace("-", "_").replace(" ", "_")
    if text in ("available", "released", "ready", "published", "ok", "live"):
        return STATUS_AVAILABLE
    return STATUS_COMING_SOON


def _version_parts(text) -> list:
    parts: list[int] = []
    for chunk in str(text or "").replace("-", ".").replace("_", ".").split("."):
        chunk = chunk.strip()
        if chunk.isdigit():
            parts.append(int(chunk))
        else:
            digits = "".join(ch for ch in chunk if ch.isdigit())
            parts.append(int(digits) if digits else 0)
    return parts


def compare_versions(a, b) -> int:
    """语义化版本比较：``a>b`` → 1；``a<b`` → -1；相等 → 0。"""
    pa, pb = _version_parts(a), _version_parts(b)
    length = max(len(pa), len(pb))
    pa += [0] * (length - len(pa))
    pb += [0] * (length - len(pb))
    if pa > pb:
        return 1
    if pa < pb:
        return -1
    return 0


@dataclass
class Release:
    """一个已发布的安装包。"""

    version: str = ""
    date: str = ""
    size: int = 0
    url: str = ""
    filename: str = ""
    notes: str = ""
    mandatory: bool = False
    sha256: str = ""

    @classmethod
    def from_dict(cls, data: Any) -> "Release":
        if not isinstance(data, dict):
            return cls()
        return cls(
            version=_text(data.get("version") or data.get("name")),
            date=_text(data.get("date") or data.get("released_at")
                       or data.get("time") or data.get("updated_at")),
            size=_int(data.get("size") or data.get("size_bytes") or data.get("bytes")),
            url=_text(data.get("url") or data.get("download") or data.get("href")),
            filename=_text(data.get("filename") or data.get("file")),
            notes=_notes(data.get("notes") or data.get("note") or data.get("changelog")),
            mandatory=bool(data.get("mandatory") or data.get("force") or False),
            sha256=_text(data.get("sha256") or data.get("sha256sum")
                         or data.get("hash") or data.get("digest")),
        )

    @property
    def size_text(self) -> str:
        try:
            return util.human_size(self.size) if self.size else ""
        except Exception:  # noqa: BLE001
            return ""


@dataclass
class PlatformInfo:
    """单个平台的发布情况。"""

    key: str
    label: str = ""
    status: str = STATUS_COMING_SOON
    note: str = ""
    releases: list = field(default_factory=list)

    @property
    def available(self) -> bool:
        return self.status == STATUS_AVAILABLE and bool(self.releases)

    @property
    def coming_soon(self) -> bool:
        return not self.available

    @property
    def latest(self) -> "Release | None":
        return self.releases[0] if self.releases else None


@dataclass
class ReleaseCatalog:
    """整套发布清单。"""

    platforms: dict = field(default_factory=dict)
    known: bool = False
    source: str = "fallback"
    fetched_at: float = 0.0

    def order(self) -> list:
        keys = [k for k in PLATFORM_ORDER if k in self.platforms]
        keys += [k for k in self.platforms if k not in keys]
        return [self.platforms[k] for k in keys]

    def platform(self, key: str) -> "PlatformInfo | None":
        return self.platforms.get(str(key))

    def latest_for(self, key: str) -> "Release | None":
        info = self.platforms.get(str(key))
        return info.latest if info is not None else None


@dataclass
class ReleaseCheck:
    """供更新检查复用的结果。"""

    known: bool = False
    available: bool = False
    version: str = ""
    release: "Release | None" = None
    message: str = ""


def _parse_platform(key: str, value: Any) -> PlatformInfo:
    label = PLATFORM_LABELS.get(key, str(key).title())
    note = ""
    status = STATUS_COMING_SOON
    raw_releases: Any = []
    if isinstance(value, dict):
        label = _text(value.get("label") or value.get("name")) or label
        note = _text(value.get("note") or value.get("message"))
        status = _norm_status(value.get("status"))
        raw_releases = (value.get("releases") or value.get("items")
                        or value.get("versions") or [])
    elif isinstance(value, list):
        raw_releases = value
    releases: list = []
    if isinstance(raw_releases, list):
        for item in raw_releases:
            release = Release.from_dict(item)
            if release.version or release.url:
                releases.append(release)
    if releases:
        status = STATUS_AVAILABLE
    return PlatformInfo(key=key, label=label, status=status, note=note, releases=releases)


def _parse_catalog(data: dict) -> dict:
    raw = data.get("platforms")
    if raw is None:
        raw = data.get("releases")
    if raw is None:
        raw = data.get("data")
    out: dict = {}
    if isinstance(raw, dict):
        for key, value in raw.items():
            out[str(key)] = _parse_platform(str(key), value)
    elif isinstance(raw, list):
        for item in raw:
            if isinstance(item, dict):
                key = _text(item.get("platform") or item.get("key") or item.get("os"))
                if key:
                    out[key] = _parse_platform(key, item)
    return out


def _fallback_platforms() -> dict:
    out: dict = {}
    for key in PLATFORM_ORDER:
        if key == "windows":
            out[key] = PlatformInfo(
                key="windows", label=PLATFORM_LABELS["windows"],
                status=STATUS_AVAILABLE, note="",
                releases=[Release(
                    version=constants.APP_VERSION,
                    url=constants.UPDATE_EXE_URL,
                    filename="forum.exe",
                    notes="Windows 桌面客户端（安装包）。")])
        else:
            out[key] = PlatformInfo(key=key, label=PLATFORM_LABELS[key],
                                    status=STATUS_COMING_SOON)
    return out


_lock = threading.RLock()
_cache: "ReleaseCatalog | None" = None


def _fetch() -> tuple:
    """拉取远端清单；返回 ``(原始字典, 是否成功)``。"""
    try:
        result = api_mod.api().get(constants.APP_RELEASES_API)
    except Exception as exc:  # noqa: BLE001
        _log.info("拉取发布清单失败：%s", exc)
        return {}, False
    if not result.ok:
        _log.info("发布清单不可用：%s", result.message)
        return {}, False
    data = result.data
    if not isinstance(data, dict):
        return {}, False
    return data, True


def platforms(refresh: bool = False) -> ReleaseCatalog:
    """获取发布清单（带 TTL 缓存；离线时返回内置兜底，``known=False``）。"""
    global _cache
    with _lock:
        cached = _cache
        if (not refresh and cached is not None
                and (time.time() - cached.fetched_at) < CACHE_TTL):
            return cached
    data, known = _fetch()
    with _lock:
        if known:
            merged = _fallback_platforms()
            merged.update(_parse_catalog(data))
            _cache = ReleaseCatalog(platforms=merged, known=True,
                                    source="server", fetched_at=time.time())
        elif _cache is not None:
            _cache.fetched_at = time.time()
        else:
            _cache = ReleaseCatalog(platforms=_fallback_platforms(), known=False,
                                    source="fallback", fetched_at=time.time())
        return _cache


def reset_cache() -> None:
    """丢掉缓存（测试或手动刷新时用）。"""
    global _cache
    with _lock:
        _cache = None


def check(current_version: str) -> ReleaseCheck:
    """基于发布清单判定 Windows 端是否有新版本。"""
    catalog = platforms()
    if not catalog.known:
        return ReleaseCheck(known=False)
    release = catalog.latest_for("windows")
    if release is None or not release.version:
        return ReleaseCheck(known=True)
    current = str(current_version or constants.APP_VERSION)
    if compare_versions(current, release.version) >= 0:
        return ReleaseCheck(known=True, available=False, version=release.version,
                            release=release, message="当前已是最新版本")
    message = "发现新版本（%s）" % release.version
    if release.size:
        message += "，大小 %s" % release.size_text
    return ReleaseCheck(known=True, available=True, version=release.version,
                        release=release, message=message)
