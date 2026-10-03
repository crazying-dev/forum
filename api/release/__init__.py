"""应用发布 / 更新蓝图（release）。

职责（全部只读 GET，任何异常都不返回 500）：
    GET /api/app/releases                        完整清单
    GET /api/app/releases/<platform>             单平台清单
    GET /api/app/check?platform=&version=        版本检查
    GET /api/app/windows/forum.exe               Windows 安装包直链（客户端 UPDATE_EXE_URL）
    GET /api/app/download/<platform>/<filename>  通用分发（目前仅 windows）
    GET /api/app/mirror/<platform>/<filename>    服务器反代：拉 GitHub 直链并流式转发

清单文件是仓库根目录的 app_releases.json（纯数据，运维直接编辑即可）；
读取 / 解析 / 编码异常一律回退到内置 DEFAULT_MANIFEST，保证客户端拿得到清单。
"""
from __future__ import annotations

import json
import os
import re
import threading
import time
from collections import OrderedDict
from urllib.parse import urlparse

import requests
from flask import (Blueprint, Response, jsonify, request, send_file,
                   stream_with_context)

import config

release_bp = Blueprint("release", __name__)

# 仓库根目录：api/release/__init__.py → api → 仓库根
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
MANIFEST_PATH = os.path.join(REPO_ROOT, "app_releases.json")

# 安装包文件名白名单（只允许常规字符，防目录穿越）
SAFE_NAME_RE = re.compile(r"^[A-Za-z0-9._-]+$")

# 内置回退清单，内容与 app_releases.json 等价（文件缺失/损坏时使用）
DEFAULT_MANIFEST: dict = {
    "schema": 1,
    "updated_at": "2026-10-03T13:35:00+08:00",
    "min_versions": {
        "windows": "1.3.13",
        "android": "1.0.10",
        "web": "0",
    },
    "platforms": [
        {
            "key": "windows",
            "name": "Windows",
            "icon": "fa-windows",
            "status": "available",
            "requirement": "Windows 10 / 11（64 位）",
            "releases": [
                {
                    "version": "1.3.13",
                    "channel": "stable",
                    "date": "2026-10-03",
                    "size": 48574686,
                    "url": "https://github.com/crazying-dev/forum/releases/download/Windows-V1.3.13/forum_setup.exe",
                    "filename": "forum_setup.exe",
                    "sha256": "98547b44a6a76e09f7c2611dee46b4b60e3b949a3e07d1f33f1a32e494de98cf",
                    "notes": [
                        "本地缓存统一 24 小时上限：过期后先用旧数据展示，再后台静默刷新，离线也能看上次内容",
                        "覆盖帖子缓存、头像与正文图片、Wiki GIF 与发布清单缓存",
                        "版本号升至 1.3.13",
                    ],
                    "mandatory": False,
                }
            ],
        },
        {
            "key": "android",
            "name": "Android",
            "icon": "fa-android",
            "status": "available",
            "requirement": "Android 7.0 及以上",
            "releases": [
                {
                    "version": "1.0.10",
                    "channel": "stable",
                    "date": "2026-10-03",
                    "size": 8119736,
                    "url": "https://github.com/crazying-dev/forum/releases/download/Android-V1.0.10/forum-android-1.0.10.apk",
                    "filename": "forum-android-1.0.10.apk",
                    "sha256": "7cbd46a86cc6dad0a42753de94a0a598fe4478276df9f8a6489add79143a8b64",
                    "notes": [
                        "本地缓存统一 24 小时上限：过期后先用旧数据展示，再后台静默刷新，离线也能看上次内容",
                        "图片磁盘缓存按 24 小时时段分目录，启动时清理过期目录",
                        "版本号 versionCode 11 / versionName 1.0.10",
                    ],
                    "mandatory": False,
                }
            ],
        },
        {
            "key": "linux",
            "name": "Linux",
            "icon": "fa-linux",
            "status": "coming_soon",
            "requirement": "x86_64 桌面发行版",
            "releases": [],
        },
        {
            "key": "macos",
            "name": "macOS",
            "icon": "fa-apple",
            "status": "coming_soon",
            "requirement": "macOS 11 及以上（Intel / Apple Silicon）",
            "releases": [],
        },
    ],
}

# 清单缓存：key 用「文件 mtime + size」，避免每次请求都读盘
_MANIFEST_CACHE: dict = {"key": None, "data": None}


# ──────────────────────────────────────────────
# 清单读取（API 与页面共用）
# ──────────────────────────────────────────────
def load_manifest() -> dict:
    """读取 app_releases.json；异常时回退内置 DEFAULT_MANIFEST（不抛异常）。"""
    try:
        stat = os.stat(MANIFEST_PATH)
        cache_key = (int(stat.st_mtime), stat.st_size)
    except OSError as e:
        print(f"[release] 清单文件不可用（{e}），使用内置默认清单")
        return DEFAULT_MANIFEST

    if _MANIFEST_CACHE.get("key") == cache_key and isinstance(_MANIFEST_CACHE.get("data"), dict):
        return _MANIFEST_CACHE["data"]

    try:
        with open(MANIFEST_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            raise ValueError("清单根节点不是 JSON 对象")
    except Exception as e:  # noqa: BLE001 — 包含 JSONDecodeError / UnicodeDecodeError
        print(f"[release] 清单解析失败（{e}），使用内置默认清单")
        return DEFAULT_MANIFEST

    _MANIFEST_CACHE["key"] = cache_key
    _MANIFEST_CACHE["data"] = data
    return data


def platforms() -> list:
    """返回平台列表（缺失或类型不对时用默认值）。"""
    value = load_manifest().get("platforms")
    if isinstance(value, list):
        return value
    return DEFAULT_MANIFEST["platforms"]


def find_platform(key) -> dict | None:
    """按 key 或 name 匹配平台（大小写不敏感），找不到返回 None。"""
    if not key or not isinstance(key, str):
        return None
    target = key.strip().lower()
    if not target:
        return None
    for platform in platforms():
        if not isinstance(platform, dict):
            continue
        if str(platform.get("key", "")).lower() == target:
            return platform
        if str(platform.get("name", "")).lower() == target:
            return platform
    return None


# ──────────────────────────────────────────────
# 版本号工具
# ──────────────────────────────────────────────
def parse_version(text):
    """把 "1.2.3" / "v1.2.3-beta" 解析成 (1, 2, 3)；只取数字段，非法返回 ()。"""
    if not isinstance(text, str):
        return ()
    raw = text.strip().lstrip("vV")
    if not raw:
        return ()
    parts: list[int] = []
    for segment in raw.split("."):
        match = re.match(r"\d+", segment.strip())
        if not match:
            break
        parts.append(int(match.group(0)))
    return tuple(parts)


def compare_versions(a, b) -> int:
    """逐段比较版本号，a < b 返回 -1，相等返回 0，a > b 返回 1（长度不同按 0 补齐）。"""
    va = parse_version(a) if isinstance(a, str) else tuple(a or ())
    vb = parse_version(b) if isinstance(b, str) else tuple(b or ())
    # 短的一方补 0，保证 "2.0" 与 "2.0.0" 相等
    size = max(len(va), len(vb))
    padded_a = va + (0,) * (size - len(va))
    padded_b = vb + (0,) * (size - len(vb))
    for x, y in zip(padded_a, padded_b):
        if x != y:
            return -1 if x < y else 1
    return 0


# ──────────────────────────────────────────────
# 最低版本闸门（客户端版本过低 → 426，客户端据此弹窗提示更新）
# ──────────────────────────────────────────────
# 客户端应在每个请求上携带：
#   X-Client-Platform: windows | android | web
#   X-Client-Version:  1.3.13
# 旧客户端没有这两个头，则从 User-Agent「CrForum-Windows/1.3.13」兜底解析。
# 清单顶层 min_versions 字典给出各平台最低版本；「web」键被忽略（网页由服务端
# 自身提供，不存在版本落后问题）。
CLIENT_PLATFORM_HEADER = "X-Client-Platform"
CLIENT_VERSION_HEADER = "X-Client-Version"
VERSION_TOO_LOW_CODE = "VERSION_TOO_LOW"
WEB_PLATFORM = "web"

# User-Agent 兜底：CrForum-Windows/1.3.13、CrForum-Android/1.0.10
CLIENT_UA_RE = re.compile(r"CrForum-([A-Za-z0-9_.-]+)/([0-9][0-9A-Za-z._-]*)")


def min_versions() -> dict:
    """清单顶层 min_versions 字典；缺失或类型不对时回退内置默认。"""
    value = load_manifest().get("min_versions")
    if isinstance(value, dict):
        return value
    fallback = DEFAULT_MANIFEST.get("min_versions")
    return fallback if isinstance(fallback, dict) else {}


def min_version_for(platform):
    """平台最低版本号（字符串）；未配置 / 为空 / web 返回 None（表示不校验）。"""
    if not isinstance(platform, str):
        return None
    key = platform.strip().lower()
    if not key or key == WEB_PLATFORM:
        return None
    value = min_versions().get(key)
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def resolve_client(headers, user_agent=""):
    """确定客户端 (平台, 版本)：优先 X-Client-* 请求头，其次 User-Agent 兜底。

    返回（小写平台名, 原始版本字符串）；无法判断时返回 ("", "")，调用方应放行。
    """
    platform = ""
    version = ""
    try:
        platform = str(headers.get(CLIENT_PLATFORM_HEADER) or "").strip()
        version = str(headers.get(CLIENT_VERSION_HEADER) or "").strip()
    except Exception:  # noqa: BLE001 — headers 不是映射时忽略
        platform, version = "", ""
    if not platform:
        match = CLIENT_UA_RE.search(user_agent or "")
        if match:
            platform = match.group(1)
            if not version:
                version = match.group(2)
    return platform.strip().lower(), version


def _download_url_for(platform) -> str:
    """该平台最新安装包直链；取不到返回空串。"""
    platform_data = find_platform(platform)
    if not platform_data:
        return ""
    latest = pick_latest(platform_data)
    if not latest:
        return ""
    return str(latest.get("url") or "")


def version_gate_violation(platform, version):
    """版本低于最低版本则返回 426 响应体；否则（含无法判断 / web）返回 None。"""
    minimum = min_version_for(platform)
    if not minimum:
        return None
    # 平台已知但版本缺失 → 视为 0，强制更新
    current = parse_version(version) or (0,)
    if compare_versions(current, minimum) >= 0:
        return None
    return {
        "success": False,
        "code": VERSION_TOO_LOW_CODE,
        "message": "版本过低，请更新",
        "platform": platform,
        "current": version or "",
        "min_version": minimum,
        "download_url": _download_url_for(platform),
        "download_page": (getattr(config, "SITE_BASE_URL", "") or "").rstrip("/") + "/Download",
    }


def should_block_request(method, path, headers, user_agent=""):
    """通用闸门判定：需要拦截时返回 426 响应体，否则返回 None。

    豁免：OPTIONS 预检；非 /api/ 路径（页面与静态资源）；/api/app/*
    （清单 / 检查 / 反代下载，保证客户端能自助更新）；web 平台；
    无法判断平台时放行（fail-open）。
    """
    if (method or "").upper() == "OPTIONS":
        return None
    if not path or not path.startswith("/api/") or path.startswith("/api/app/"):
        return None
    platform, version = resolve_client(headers, user_agent)
    return version_gate_violation(platform, version)


def pick_latest(platform) -> dict | None:
    """取平台上版本号最大的 release；优先 channel == 'stable'，没有 stable 就取全部。"""
    if not isinstance(platform, dict):
        return None
    releases = platform.get("releases")
    if not isinstance(releases, list) or not releases:
        return None
    items = [r for r in releases if isinstance(r, dict)]
    stable = [r for r in items if r.get("channel") == "stable"]
    pool = stable or items
    if not pool:
        return None
    best = pool[0]
    for release in pool[1:]:
        if compare_versions(release.get("version", ""), best.get("version", "")) > 0:
            best = release
    return best


def human_size(n) -> str:
    """字节数格式化为 B/KB/MB/GB（保留 1 位小数）。"""
    try:
        value = float(n)
    except (TypeError, ValueError):
        return ""
    if value <= 0:
        return ""
    units = ["B", "KB", "MB", "GB", "TB"]
    index = 0
    while value >= 1024 and index < len(units) - 1:
        value /= 1024.0
        index += 1
    if index == 0:
        return f"{int(value)} B"
    return f"{value:.1f} {units[index]}"


# ──────────────────────────────────────────────
# 接口：清单 / 单平台 / 版本检查
# ──────────────────────────────────────────────
@release_bp.route("/releases", methods=["GET"])
def list_releases():
    """完整清单。"""
    data = load_manifest()
    return jsonify({
        "success": True,
        "schema": data.get("schema", 1),
        "updated_at": data.get("updated_at", ""),
        "min_versions": min_versions(),
        "platforms": platforms(),
    }), 200


@release_bp.route("/releases/<platform>", methods=["GET"])
def platform_releases(platform: str):
    """单个平台清单；未知平台 404。"""
    found = find_platform(platform)
    if not found:
        return jsonify({"success": False, "message": "未知平台"}), 404
    return jsonify({"success": True, "platform": found}), 200


@release_bp.route("/check", methods=["GET"])
def check_update():
    """版本检查：告诉客户端是否有新版本。"""
    key = (request.args.get("platform") or "").strip() or "windows"
    current = (request.args.get("version") or "").strip() or "0.0.0"

    found = find_platform(key)
    if not found:
        return jsonify({"success": False, "message": "未知平台"}), 404

    minimum = min_version_for(found.get("key", key))

    payload = {
        "success": True,
        "platform": found.get("key", key),
        "current": current,
        "latest": None,
        "available": False,
        "mandatory": False,
        "release": None,
        "min_version": minimum or "",
        "too_low": bool(minimum and compare_versions(current, minimum) < 0),
        "message": "当前已是最新版本",
    }

    status = found.get("status")
    releases = found.get("releases")
    if status != "available" or not isinstance(releases, list) or not releases:
        payload["message"] = "该平台暂未发布"
        return jsonify(payload), 200

    latest = pick_latest(found)
    if not latest:
        payload["message"] = "该平台暂未发布"
        return jsonify(payload), 200

    latest_version = str(latest.get("version", ""))
    payload["latest"] = latest_version
    if compare_versions(latest_version, current) > 0:
        payload["available"] = True
        payload["mandatory"] = bool(latest.get("mandatory", False))
        payload["release"] = latest
        payload["message"] = f"发现新版本 {latest_version}"
    return jsonify(payload), 200


# ──────────────────────────────────────────────
# 安装包分发
# ──────────────────────────────────────────────
def _safe_release_path(filename) -> str | None:
    """白名单 + realpath 校验，返回安全的安装包绝对路径；非法返回 None。"""
    directory = getattr(config, "APP_RELEASE_DIR", "") or ""
    if not directory or not isinstance(filename, str) or not SAFE_NAME_RE.match(filename):
        return None
    base = os.path.realpath(directory)
    target = os.path.realpath(os.path.join(base, filename))
    # 必须在发布目录之内（防 ../ 目录穿越）
    if target != base and not target.startswith(base + os.sep):
        return None
    return target


def _send_release(filename):
    """发送安装包：conditional=True 交给 Werkzeug 处理 Range / 断点续传。"""
    path = _safe_release_path(filename)
    if not path or not os.path.isfile(path):
        return jsonify({"success": False, "message": "安装包暂未上传到服务器"}), 503
    # as_attachment 让浏览器下载而非内嵌；max_age=0 不强缓存；conditional 支持 Range
    return send_file(path, as_attachment=True, conditional=True, max_age=0)


@release_bp.route("/windows/forum.exe", methods=["GET"])
def download_windows_exe():
    """Windows 客户端安装包直链（客户端 UPDATE_EXE_URL 常量指向这里）。"""
    return _send_release("forum.exe")


@release_bp.route("/download/<platform>/<filename>", methods=["GET"])
def download_release(platform: str, filename: str):
    """通用安装包分发（目前仅 windows 有包）。"""
    if (platform or "").strip().lower() != "windows":
        return jsonify({"success": False, "message": "该平台暂未发布"}), 404
    return _send_release(filename)


# ──────────────────────────────────────────────
# 服务器反代（/Download 页与客户端的统一下载入口）
# ──────────────────────────────────────────────
# 只允许反代 GitHub 上的安装包，避免本接口被当成任意代理（SSRF）
MIRROR_HOSTS = ("github.com", "githubusercontent.com", "githubassets.com")
MIRROR_TIMEOUT = (10, 120)
MIRROR_CHUNK = 64 * 1024

# ── 进程内内存缓存 ──
# 24 小时 TTL；只活在当前进程内存里，不落盘、不跨 worker 共享，重启即全部丢失。
MIRROR_TTL = 24 * 3600
MIRROR_CACHE_MAX_BYTES = 256 * 1024 * 1024   # 总容量上限，超出按 LRU 淘汰
MIRROR_CACHE_MAX_FILE = 128 * 1024 * 1024    # 单文件上限，超过则不缓存（仍正常转发）
_MIRROR_CACHE: "OrderedDict[str, dict]" = OrderedDict()
_MIRROR_LOCK = threading.Lock()
_MIRROR_STATS = {"hit": 0, "miss": 0, "stored": 0, "evicted": 0, "skipped": 0}


def _cache_bytes() -> int:
    """当前缓存占用字节数（调用方需已持有 _MIRROR_LOCK）。"""
    return sum(len(entry["data"]) for entry in _MIRROR_CACHE.values())


def _cache_get(url: str) -> dict | None:
    """读缓存：命中则刷新 LRU 顺序；过期条目顺手删除。"""
    now = time.time()
    with _MIRROR_LOCK:
        entry = _MIRROR_CACHE.get(url)
        if entry is None:
            _MIRROR_STATS["miss"] += 1
            return None
        if now - entry["ts"] > MIRROR_TTL:
            del _MIRROR_CACHE[url]
            _MIRROR_STATS["miss"] += 1
            return None
        _MIRROR_CACHE.move_to_end(url)
        _MIRROR_STATS["hit"] += 1
        return entry


def _cache_put(url: str, data: bytes, content_type: str,
               etag: str = "", last_modified: str = "") -> None:
    """写入缓存；超出总容量时按 LRU 淘汰到够用为止。"""
    if not data or len(data) > MIRROR_CACHE_MAX_FILE:
        with _MIRROR_LOCK:
            _MIRROR_STATS["skipped"] += 1
        return
    with _MIRROR_LOCK:
        _MIRROR_CACHE[url] = {
            "data": data,
            "ts": time.time(),
            "content_type": content_type,
            "etag": etag,
            "last_modified": last_modified,
        }
        _MIRROR_CACHE.move_to_end(url)
        _MIRROR_STATS["stored"] += 1
        while _cache_bytes() > MIRROR_CACHE_MAX_BYTES and len(_MIRROR_CACHE) > 1:
            _MIRROR_CACHE.popitem(last=False)
            _MIRROR_STATS["evicted"] += 1


def cache_info() -> dict:
    """缓存现状快照（诊断 / 测试用）。"""
    with _MIRROR_LOCK:
        info = {
            "entries": len(_MIRROR_CACHE),
            "bytes": _cache_bytes(),
            "ttl": MIRROR_TTL,
            "max_bytes": MIRROR_CACHE_MAX_BYTES,
            "max_file": MIRROR_CACHE_MAX_FILE,
        }
        info.update(_MIRROR_STATS)
        return info


def cache_clear() -> int:
    """清空缓存，返回被清掉的条目数。"""
    with _MIRROR_LOCK:
        count = len(_MIRROR_CACHE)
        _MIRROR_CACHE.clear()
        return count


def _mirror_target(platform, filename) -> str | None:
    """按发布清单找到指定文件名的 GitHub 直链；平台/文件名不匹配一律返回 None。"""
    key = str(platform or "").strip().lower()
    name = str(filename or "").strip()
    if not key or not name or not SAFE_NAME_RE.match(name):
        return None
    for item in platforms():
        if not isinstance(item, dict):
            continue
        if str(item.get("key", "")).lower() != key:
            continue
        for release in item.get("releases") or []:
            if not isinstance(release, dict):
                continue
            url = str(release.get("url") or "").strip()
            if not url:
                continue
            candidate = str(release.get("filename") or "").strip() \
                or os.path.basename(urlparse(url).path)
            if candidate != name:
                continue
            host = (urlparse(url).hostname or "").lower()
            if url.startswith("https://") and any(
                    host == h or host.endswith("." + h) for h in MIRROR_HOSTS):
                return url
    return None


def is_mirrorable(url) -> bool:
    """该直链是否允许走本站反代（https + GitHub 域名白名单）。"""
    text = str(url or "").strip()
    if not text.startswith("https://"):
        return False
    host = (urlparse(text).hostname or "").lower()
    return any(host == h or host.endswith("." + h) for h in MIRROR_HOSTS)


def _parse_range(range_header, total: int):
    """解析单段 Range（bytes=a-b / a- / -n），返回闭区间 (start, end)；不合法返回 None。"""
    if not range_header or not isinstance(range_header, str):
        return None
    header = range_header.strip()
    if not header.lower().startswith("bytes=") or "," in header:
        return None
    first, sep, last = header[6:].strip().partition("-")
    if not sep:
        return None
    first, last = first.strip(), last.strip()
    try:
        if first == "":
            size = int(last)
            if size <= 0:
                return None
            start, end = max(0, total - size), total - 1
        else:
            start = int(first)
            end = int(last) if last else total - 1
    except ValueError:
        return None
    if start < 0 or start >= total:
        return None
    end = min(end, total - 1)
    if end < start:
        return None
    return start, end


def _mirror_headers(filename, content_type="", etag="", last_modified="") -> dict:
    """反代响应的公共头。Cache-Control 与进程内缓存 TTL 对齐。"""
    headers = {
        "Accept-Ranges": "bytes",
        "Content-Disposition": 'attachment; filename="%s"' % filename,
        "Content-Type": content_type or "application/octet-stream",
        "Cache-Control": "public, max-age=%d" % MIRROR_TTL,
    }
    if etag:
        headers["ETag"] = etag
    if last_modified:
        headers["Last-Modified"] = last_modified
    return headers


def _serve_cached(entry, filename, range_header):
    """命中缓存：整文件 200 / 单段 Range 206 / 越界 416，全部从内存切片。"""
    data = entry["data"]
    total = len(data)
    headers = _mirror_headers(filename, entry.get("content_type", ""),
                              entry.get("etag", ""), entry.get("last_modified", ""))
    parsed = _parse_range(range_header, total)
    if range_header and parsed is None:
        return Response(status=416, headers={"Content-Range": "bytes */%d" % total,
                                             "Accept-Ranges": "bytes"})
    if parsed is None:
        headers["Content-Length"] = str(total)
        return Response(data, status=200, headers=headers)
    start, end = parsed
    headers["Content-Range"] = "bytes %d-%d/%d" % (start, end, total)
    headers["Content-Length"] = str(end - start + 1)
    return Response(data[start:end + 1], status=206, headers=headers)


def _stream_and_cache(url, upstream, content_type, etag, last_modified):
    """边转发边累积；只有完整收完才写入缓存（客户端中断则丢弃）。"""
    buffer = bytearray()
    cacheable = True
    complete = False
    try:
        for chunk in upstream.iter_content(MIRROR_CHUNK):
            if not chunk:
                continue
            if cacheable:
                buffer.extend(chunk)
                if len(buffer) > MIRROR_CACHE_MAX_FILE:
                    cacheable = False
                    buffer = bytearray()
            yield chunk
        complete = True
    finally:
        upstream.close()
        if complete and cacheable and buffer:
            _cache_put(url, bytes(buffer), content_type, etag, last_modified)


@release_bp.route("/mirror/<platform>/<filename>", methods=["GET"])
def mirror_release(platform: str, filename: str):
    """站内统一下载入口：服务端反代 GitHub 直链，带进程内 24 小时内存缓存。

    - 命中缓存：直接从内存切片返回（支持 Range 断点续传）
    - 未命中：边转发边累积，完整收完后才写入缓存（客户端中断则丢弃，不留脏数据）
    - 缓存只活在当前进程内存里，不落盘，进程重启即全部丢失
    任何异常都返回 JSON，不返回 500。
    """
    url = _mirror_target(platform, filename)
    if not url:
        return jsonify({"success": False, "message": "暂无可反代的安装包"}), 404

    range_header = request.headers.get("Range")
    cached = _cache_get(url)
    if cached is not None:
        return _serve_cached(cached, filename, range_header)

    upstream_headers = {
        "User-Agent": request.headers.get("User-Agent") or "CrForum-Mirror",
        "Accept-Encoding": "identity",
    }
    if range_header:
        upstream_headers["Range"] = range_header
    try:
        upstream = requests.get(url, headers=upstream_headers, stream=True,
                                timeout=MIRROR_TIMEOUT, allow_redirects=True)
    except Exception as e:  # noqa: BLE001
        print(f"[release] 反代拉取失败（{url}）：{e}")
        return jsonify({"success": False, "message": f"上游拉取失败：{e}"}), 502
    if upstream.status_code >= 400:
        code = upstream.status_code
        upstream.close()
        return jsonify({"success": False, "message": f"上游返回 {code}"}), 502

    content_type = upstream.headers.get("Content-Type") or ""
    etag = upstream.headers.get("ETag") or ""
    last_modified = upstream.headers.get("Last-Modified") or ""
    headers = _mirror_headers(filename, content_type, etag, last_modified)

    # 带 Range 的上游响应是片段，不能当作完整文件缓存；仅透传，等整包下载时再入缓存
    if range_header or upstream.status_code == 206:
        for key in ("Content-Length", "Content-Range"):
            value = upstream.headers.get(key)
            if value:
                headers[key] = value
        return Response(stream_with_context(_relay(upstream)),
                        status=upstream.status_code, headers=headers,
                        direct_passthrough=True)

    total = upstream.headers.get("Content-Length")
    if total:
        headers["Content-Length"] = total
    return Response(
        stream_with_context(
            _stream_and_cache(url, upstream, content_type, etag, last_modified)),
        status=upstream.status_code, headers=headers, direct_passthrough=True)


@release_bp.route("/cache", methods=["GET"])
def mirror_cache_info():
    """反代缓存诊断（只读）：条目数 / 占用字节 / TTL / 命中统计。"""
    return jsonify({"success": True, **cache_info()}), 200


def _relay(upstream):
    """透传上游响应体（不缓存），结束或中断都确保关闭上游连接。"""
    try:
        for chunk in upstream.iter_content(MIRROR_CHUNK):
            if chunk:
                yield chunk
    finally:
        upstream.close()
