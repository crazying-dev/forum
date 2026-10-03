# -*- coding: utf-8 -*-
"""帖子本地缓存：``~/.Cr/forum/cache/post/<帖子 ID>.json``。

策略（V1.3.3 需求）：

* **本地优先**：进帖先渲染本地缓存（秒开），随后一律联网刷新并覆盖缓存；
* 互动数据（点赞数 / 是否已赞 / 是否已收藏 / 首屏评论）与正文存在同一条记录里，
  因此「联网状态下再次进入本帖」会一并重新获取；
* 请求失败时保留旧缓存，页面上给出提示——离线也能看到上次的内容；
* **缓存最多保留 24 小时**（V1.3.13，见 :mod:`app.cachepolicy`）：超过 24 小时的缓存
  仍可先渲染（保底 / 离线可用），但 :func:`is_stale` 会返回 True，调用方需重新拉取。

写入使用「临时文件 + 原子替换」避免半截文件；文件名经 :func:`paths.safe_component`
清洗，防止帖子 ID 里的路径分隔符逃出缓存目录。
"""

from __future__ import annotations

import json
import os
import threading
import time
from pathlib import Path
from typing import Any

from . import cachepolicy, logger, paths

_log = logger.get_logger("postcache")

SCHEMA_VERSION = 1
MAX_ENTRIES = 300          # 最多保留多少篇帖子的缓存
MAX_AGE = cachepolicy.MAX_AGE_SECONDS   # 单条缓存最多保留 24 小时
_EXT = ".json"
_lock = threading.RLock()


def cache_dir() -> Path:
    """缓存目录（:func:`paths.post_cache_dir`）。"""
    return paths.post_cache_dir()


def path_for(post_id: str) -> Path:
    """帖子 ID → 缓存文件路径（ID 经清洗，杜绝目录穿越）。"""
    name = paths.safe_component(post_id, fallback="post")
    return cache_dir() / (name + _EXT)


def _read(path: Path) -> dict | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    return data if isinstance(data, dict) else None


def load(post_id: str) -> dict | None:
    """读取缓存；不存在 / 损坏 / 无正文时返回 ``None``。"""
    if not post_id:
        return None
    record = _read(path_for(post_id))
    if not record or not isinstance(record.get("post"), dict) or not record["post"]:
        return None
    return record


def saved_at(post_id: str) -> float:
    """缓存写入时间戳（秒）；无缓存返回 ``0``。"""
    record = _read(path_for(post_id))
    try:
        return float((record or {}).get("saved_at") or 0.0)
    except (TypeError, ValueError):
        return 0.0


def age(post_id: str) -> float:
    """缓存年龄（秒）；无缓存返回 ``-1``。"""
    stamp = saved_at(post_id)
    if stamp <= 0:
        return -1.0
    return max(time.time() - stamp, 0.0)


def is_stale(post_id: str) -> bool:
    """缓存是否已超过 :data:`MAX_AGE`（默认 24 小时）。

    无缓存 / 无时间戳时返回 ``False``（交由调用方按「没有缓存」处理）。
    过期不代表不可用：应先渲染旧数据，再联网刷新覆盖。
    """
    return cachepolicy.is_stale_timestamp(saved_at(post_id))


def save(post_id: str, **fields: Any) -> bool:
    """写入缓存；只覆盖显式传入的字段，未传的沿用旧值。

    典型用法：``save(pid, post=..., liked=..., favorited=..., comments=[...])``。
    """
    if not post_id:
        return False
    with _lock:
        path = path_for(post_id)
        record = _read(path)
        if not isinstance(record, dict):
            record = {}
        record.setdefault("version", SCHEMA_VERSION)
        record["post_id"] = str(post_id)
        for key, value in fields.items():
            if value is not None:
                record[key] = value
        if not isinstance(record.get("post"), dict) or not record["post"]:
            return False
        record["saved_at"] = time.time()
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp = path.with_suffix(path.suffix + ".part")
            tmp.write_text(json.dumps(record, ensure_ascii=False), encoding="utf-8")
            os.replace(tmp, path)
        except Exception as exc:  # noqa: BLE001
            _log.warning("帖子缓存写入失败：%s", exc)
            return False
        _prune()
        return True


def drop(post_id: str) -> bool:
    """删除某篇帖子的缓存（帖子被删除 / 清理时用）。"""
    if not post_id:
        return False
    with _lock:
        try:
            path_for(post_id).unlink()
            return True
        except OSError:
            return False


def clear() -> int:
    """清空全部帖子缓存，返回删除的文件数。"""
    count = 0
    with _lock:
        folder = cache_dir()
        if not folder.is_dir():
            return 0
        for item in folder.glob("*" + _EXT):
            try:
                item.unlink()
                count += 1
            except OSError:
                pass
    return count


def count() -> int:
    """当前缓存条目数。"""
    folder = cache_dir()
    if not folder.is_dir():
        return 0
    return len(list(folder.glob("*" + _EXT)))


def _prune() -> None:
    """超过 :data:`MAX_ENTRIES` 时按修改时间删掉最旧的缓存。"""
    try:
        files = sorted(cache_dir().glob("*" + _EXT), key=lambda p: p.stat().st_mtime)
    except Exception:  # noqa: BLE001
        return
    excess = len(files) - MAX_ENTRIES
    for item in files[:max(excess, 0)]:
        try:
            item.unlink()
        except OSError:
            pass
