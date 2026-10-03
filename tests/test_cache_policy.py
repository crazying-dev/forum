# -*- coding: utf-8 -*-
"""V1.3.13 新增：本地缓存「最多 24 小时」统一策略的离线用例。

覆盖 :mod:`app.cachepolicy` 的纯函数，以及帖子缓存 / 图片缓存接入后的过期判定：

* 上限 24 小时（:data:`MAX_AGE_SECONDS` == 86400）；
* 过期后**先显示旧数据**，再后台静默重取（不删旧文件 / 离线仍可用）。

不依赖 pytest：``tests/run_tests.py`` 以无参形式逐个调用用例函数。
"""

from __future__ import annotations

import json
import os
import tempfile
import time
from pathlib import Path

from app import cachepolicy, constants, paths, postcache


# ────────────────────── 小工具 ──────────────────────


def _qt():
    from PyQt6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


def _body(post_id: str = "P1") -> dict:
    return {"id": post_id, "title": "标题", "content": "正文内容", "likes": 3}


_PATCHES: list = []


def _patch(obj, name, value) -> None:
    had = hasattr(obj, name)
    old = getattr(obj, name, None)
    _PATCHES.append((obj, name, had, old))
    setattr(obj, name, value)


def _restore_all() -> None:
    while _PATCHES:
        obj, name, had, old = _PATCHES.pop()
        if had:
            setattr(obj, name, old)
        else:
            try:
                delattr(obj, name)
            except AttributeError:
                pass


def _temp_dir(prefix: str) -> Path:
    return Path(tempfile.mkdtemp(prefix=prefix))


def _clean(folder: Path) -> None:
    try:
        for item in folder.glob("*"):
            try:
                item.unlink()
            except OSError:
                pass
        folder.rmdir()
    except OSError:
        pass


# ────────────────────── 纯函数 ──────────────────────


def test_cache_policy_max_age_is_24_hours():
    assert cachepolicy.MAX_AGE_SECONDS == 24 * 60 * 60 == 86400


def test_is_stale_timestamp_boundaries():
    now = 1_800_000_000.0
    assert cachepolicy.is_stale_timestamp(now, now) is False
    assert cachepolicy.is_stale_timestamp(now - 86399, now) is False
    assert cachepolicy.is_stale_timestamp(now - 86400, now) is False   # 恰好 24h 不算过期
    assert cachepolicy.is_stale_timestamp(now - 86401, now) is True
    assert cachepolicy.is_stale_timestamp(0, now) is False             # 无时间信息
    assert cachepolicy.is_stale_timestamp(-5, now) is False
    assert cachepolicy.is_stale_timestamp(None, now) is False
    assert cachepolicy.is_stale_timestamp("oops", now) is False


def test_is_stale_file_uses_mtime():
    folder = _temp_dir("crforum-age-")
    target = folder / "a.png"
    target.write_bytes(b"x")
    try:
        assert cachepolicy.is_stale_file(target) is False
        old = time.time() - cachepolicy.MAX_AGE_SECONDS - 60
        os.utime(target, (old, old))
        assert cachepolicy.is_stale_file(target) is True
        assert cachepolicy.is_stale_file(folder / "missing.png") is False
    finally:
        _clean(folder)


def test_local_cache_max_age_is_unified():
    """帖子缓存 / 图片缓存 / 发布清单缓存必须共用同一个 24 小时上限。"""
    from app import releases
    from app.widgets import images
    assert cachepolicy.MAX_AGE_SECONDS == 86400
    assert postcache.MAX_AGE == cachepolicy.MAX_AGE_SECONDS
    assert images.MAX_AGE == cachepolicy.MAX_AGE_SECONDS
    assert releases.CACHE_TTL == cachepolicy.MAX_AGE_SECONDS


# ────────────────────── 帖子缓存 ──────────────────────


def test_postcache_exposes_stale_detection():
    pid = "P-stale"
    try:
        postcache.drop(pid)
        assert postcache.is_stale(pid) is False            # 无缓存
        assert postcache.save(pid, post=_body(pid)) is True
        assert postcache.is_stale(pid) is False            # 刚写入

        path = postcache.path_for(pid)
        record = json.loads(path.read_text(encoding="utf-8"))
        record["saved_at"] = time.time() - postcache.MAX_AGE - 120
        path.write_text(json.dumps(record, ensure_ascii=False), encoding="utf-8")

        assert postcache.load(pid) is not None             # 过期仍可读（先用旧数据）
        assert path.is_file()                              # 过期不删文件（离线兜底）
        assert postcache.is_stale(pid) is True
    finally:
        postcache.drop(pid)


def test_post_cache_dir_under_cache():
    assert paths.post_cache_dir() == paths.cache_dir() / "post"


# ────────────────────── 图片缓存 ──────────────────────


def test_image_cache_age_and_stale():
    from app.widgets.images import ImageCache
    _qt()
    folder = _temp_dir("crforum-img-")
    cache = ImageCache(folder)
    url = "https://example.invalid/stale.png"
    try:
        assert cache.local(url) == ""
        assert cache.age(url) == -1.0
        assert cache.stale(url) is False                   # 无文件 ≠ 过期

        path = cache.path_for(url)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"png")
        assert cache.local(url) != ""
        assert cache.stale(url) is False

        old = time.time() - cachepolicy.MAX_AGE_SECONDS - 30
        os.utime(path, (old, old))
        assert cache.stale(url) is True
        assert cache.age(url) > cachepolicy.MAX_AGE_SECONDS
        assert cache.local(url) != ""                      # 过期不阻碍使用旧图
    finally:
        _clean(folder)


def test_avatar_refreshes_when_cache_expired():
    """头像本地缓存超过 24 小时：仍先显示旧图，同时后台静默重取。"""
    from PyQt6.QtGui import QPixmap
    from app.widgets.images import Avatar, avatar_cache
    _qt()
    url = "https://example.invalid/avatar-stale.png"
    absolute = constants.absolute(url)
    calls = []
    _patch(avatar_cache, "cached_pixmap", lambda u: QPixmap(4, 4))
    _patch(avatar_cache, "stale", lambda u: True)
    _patch(avatar_cache, "fetch",
           lambda u, on_ready=None, on_error=None, force=False:
           calls.append((u, bool(force))) or "")
    try:
        Avatar(24).set_url(url)
        assert calls == [(absolute, True)]
    finally:
        _restore_all()


def test_avatar_keeps_cache_when_fresh():
    """未过期时命中间缓存就不联网（与原有行为一致）。"""
    from PyQt6.QtGui import QPixmap
    from app.widgets.images import Avatar, avatar_cache
    _qt()
    url = "https://example.invalid/avatar-fresh.png"
    calls = []
    _patch(avatar_cache, "cached_pixmap", lambda u: QPixmap(4, 4))
    _patch(avatar_cache, "stale", lambda u: False)
    _patch(avatar_cache, "fetch",
           lambda u, on_ready=None, on_error=None, force=False:
           calls.append((u, bool(force))) or "")
    try:
        Avatar(24).set_url(url)
        assert calls == []
    finally:
        _restore_all()
