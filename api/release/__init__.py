"""应用发布 / 更新蓝图（release）。

职责（全部只读 GET，任何异常都不返回 500）：
    GET /api/app/releases                        完整清单
    GET /api/app/releases/<platform>             单平台清单
    GET /api/app/check?platform=&version=        版本检查
    GET /api/app/windows/forum.exe               Windows 安装包直链（客户端 UPDATE_EXE_URL）
    GET /api/app/download/<platform>/<filename>  通用分发（目前仅 windows）

清单文件是仓库根目录的 app_releases.json（纯数据，运维直接编辑即可）；
读取 / 解析 / 编码异常一律回退到内置 DEFAULT_MANIFEST，保证客户端拿得到清单。
"""
from __future__ import annotations

import json
import os
import re

from flask import Blueprint, jsonify, request, send_file

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
    "updated_at": "2026-09-26T20:40:00+08:00",
    "platforms": [
        {
            "key": "windows",
            "name": "Windows",
            "icon": "fa-windows",
            "status": "available",
            "requirement": "Windows 10 / 11（64 位）",
            "releases": [
                {
                    "version": "1.3.0",
                    "channel": "stable",
                    "date": "2026-09-26",
                    "size": 48521108,
                    "url": "https://www.yjlt.top/api/app/windows/forum.exe",
                    "sha256": "7ff129096a344950154f798a5676dc3a5767e619b460cf4054535f78a71acb19",
                    "notes": [
                        "修复个人主页帖子显示「匿名用户」+ 默认头像的问题（V1.3.0）",
                        "服务端 /api/user/<id>/posts 补全作者字段（user_id / user_name / user_avatar）",
                        "客户端个人主页帖子卡片对历史接口做作者信息兜底",
                        "主程序与安装包均写入 1.3.0 版本信息，文件属性可直接查看",
                    ],
                    "mandatory": False,
                }
            ],
        },
        {
            "key": "android",
            "name": "Android",
            "icon": "fa-android",
            "status": "coming_soon",
            "requirement": "Android 8.0 及以上",
            "releases": [],
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

    payload = {
        "success": True,
        "platform": found.get("key", key),
        "current": current,
        "latest": None,
        "available": False,
        "mandatory": False,
        "release": None,
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
