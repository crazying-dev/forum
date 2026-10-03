# -*- coding: utf-8 -*-
"""本地缓存统一时效策略：任何本地持久缓存**最多保留 24 小时**（V1.3.13）。

统一口径（帖子缓存 / 头像与图片缓存 / 发布清单缓存一致）：

* **上限 24 小时**：每条缓存都带写入时间（时间戳或文件 mtime），
  超过 :data:`MAX_AGE_SECONDS` 即视为「过期」；
* **过期先用旧数据**：过期不妨碍使用——先把旧数据渲染出来（秒开、离线可用），
  随后在后台静默重新拉取，拿到新数据后再覆盖缓存；
* **失败保留旧数据**：刷新失败（离线 / 4xx / 5xx）一律保留旧缓存，不清空。

本模块只放纯函数与常量，不依赖 Qt 与网络，方便单测。
"""

from __future__ import annotations

import time

#: 本地缓存最多保留多久（秒）——24 小时。
MAX_AGE_SECONDS = 24 * 60 * 60


def is_stale_timestamp(stamp: float, now: float | None = None) -> bool:
    """时间戳（秒）是否已超过 :data:`MAX_AGE_SECONDS`。

    ``stamp <= 0`` 视为「没有时间信息」，返回 ``False``（不误判为过期）。
    """
    try:
        value = float(stamp)
    except (TypeError, ValueError):
        return False
    if value <= 0:
        return False
    current = time.time() if now is None else float(now)
    return (current - value) > MAX_AGE_SECONDS


def is_stale_file(path, now: float | None = None) -> bool:
    """文件的 mtime 是否已超过 :data:`MAX_AGE_SECONDS`；文件不存在返回 ``False``。"""
    try:
        stamp = path.stat().st_mtime
    except OSError:
        return False
    return is_stale_timestamp(stamp, now)
