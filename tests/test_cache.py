# -*- coding: utf-8 -*-
"""V1.3.3 新增能力的离线用例：帖子缓存 / 启动「支持作者」弹窗 / 头像强制刷新。

不依赖 pytest：``tests/run_tests.py`` 以无参形式逐个调用用例函数。
"""

from __future__ import annotations

import inspect
from pathlib import Path

from app import config as config_mod
from app import constants, paths, postcache


# ────────────────────── 手工打桩（保存/恢复） ──────────────────────

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


def _qt():
    from PyQt6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


def _body(post_id: str = "P1") -> dict:
    return {"id": post_id, "title": "标题", "content": "正文内容", "likes": 3}


def _sample(post_id: str = "P1") -> dict:
    return {
        "post": _body(post_id),
        "liked": False,
        "favorited": False,
        "comments": [{"id": "C1"}],
    }


# ────────────────────── 路径 ──────────────────────


def test_post_cache_dir_under_cache():
    assert paths.post_cache_dir() == paths.cache_dir() / "post"
    assert paths.post_cache_dir() in paths.all_dirs()
    assert paths.post_cache_dir().name == "post"


# ────────────────────── 帖子缓存 ──────────────────────


def test_postcache_roundtrip_and_merge():
    pid = "P-roundtrip"
    try:
        assert postcache.load(pid) is None
        assert postcache.save(pid, **_sample(pid)) is True
        record = postcache.load(pid)
        assert record["post"]["title"] == "标题"
        assert record["post"]["content"] == "正文内容"
        assert record["comments"] == [{"id": "C1"}]
        assert record["liked"] is False
        assert record["saved_at"] > 0
        assert postcache.age(pid) >= 0.0
        # 只覆盖显式传入的字段：未传的（comments / 正文）应当保留
        assert postcache.save(pid, liked=True) is True
        record = postcache.load(pid)
        assert record["liked"] is True
        assert record["comments"] == [{"id": "C1"}]
        assert record["post"]["likes"] == 3
    finally:
        postcache.drop(pid)


def test_postcache_requires_body():
    pid = "P-nobody"
    try:
        assert postcache.save(pid, liked=True) is False      # 无正文不落盘
        assert postcache.load(pid) is None
        assert postcache.save("", post=_body()) is False
        assert postcache.load("") is None
        assert postcache.drop("") is False
    finally:
        postcache.drop(pid)


def test_postcache_path_is_sanitized():
    evil = "../../evil/../x"
    path = postcache.path_for(evil)
    assert path.parent == postcache.cache_dir()
    assert ".." not in path.name
    assert path.name.endswith(".json")
    try:
        assert postcache.save(evil, post=_body()) is True
        assert postcache.load(evil) is not None
        assert path.is_file()
    finally:
        postcache.drop(evil)
    assert not (paths.cache_dir().parent / "evil").exists()


def test_postcache_drop_clear_count():
    try:
        postcache.clear()
        for i in range(3):
            assert postcache.save("P-count-%d" % i, post=_body()) is True
        assert postcache.count() == 3
        assert postcache.drop("P-count-0") is True
        assert postcache.drop("P-count-0") is False
        assert postcache.count() == 2
        assert postcache.clear() == 2
        assert postcache.count() == 0
    finally:
        postcache.clear()


def test_postcache_prune_keeps_newest():
    try:
        postcache.clear()
        _patch(postcache, "MAX_ENTRIES", 2)
        for i in range(5):
            postcache.save("P-prune-%d" % i, post=_body())
        assert postcache.count() <= 2
        assert postcache.count() >= 1
    finally:
        _restore_all()
        postcache.clear()


def test_postcache_tolerates_corrupt_file():
    pid = "P-corrupt"
    path = postcache.path_for(pid)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("{ not json", encoding="utf-8")
        assert postcache.load(pid) is None
        assert postcache.saved_at(pid) == 0.0
        assert postcache.age(pid) == -1.0
        assert postcache.save(pid, post=_body()) is True     # 坏文件可被覆盖
        assert postcache.load(pid)["post"]["id"] == "P1"
    finally:
        postcache.drop(pid)


# ────────────────────── 启动「支持作者」弹窗 ──────────────────────


def test_promo_text_mentions_count():
    from app.widgets.promo import promo_text
    text = promo_text(7)
    assert "第 7 次" in text
    assert constants.APP_NAME in text


def test_promo_probability_gate():
    from app.widgets import promo
    assert promo.should_show(rand=0.0) is True
    assert promo.should_show(probability=0.3, rand=0.2999) is True
    assert promo.should_show(probability=0.3, rand=0.3) is False    # 边界不含
    assert promo.should_show(probability=0.3, rand=0.99) is False
    assert promo.should_show(probability=0.0, rand=0.0) is False
    assert promo.should_show(probability=1.0, rand=0.999) is True
    assert 0.0 < constants.PROMO_PROBABILITY <= 1.0
    assert constants.PROMO_QR_URL.startswith("https://")


def test_promo_launch_count_persists():
    from app.widgets.promo import bump_launch_count
    path = Path(paths.data_dir()) / "_promo_test_config.json"
    cfg = config_mod.Config(path)
    try:
        assert int(cfg.get("launch_count", 0)) == 0
        assert bump_launch_count(cfg) == 1
        assert bump_launch_count(cfg) == 2
        assert int(config_mod.Config(path).get("launch_count", 0)) == 2
    finally:
        try:
            path.unlink()
        except OSError:
            pass


def test_promo_maybe_show_skips_when_unlucky():
    from app.widgets import promo
    _qt()
    assert promo.maybe_show(None, count=3, rand=0.99) is False


def test_main_wires_promo():
    source = (Path(__file__).resolve().parents[1] / "main.py").read_text(encoding="utf-8")
    assert "_start_promo" in source
    assert "bump_launch_count" in source
    assert "maybe_show" in source


# ────────────────────── 头像强制刷新 ──────────────────────


def test_avatar_force_refetches_even_when_cached():
    from PyQt6.QtGui import QPixmap
    from app.widgets.images import Avatar, avatar_cache
    _qt()
    url = "https://example.invalid/avatar-force.png"
    absolute = constants.absolute(url)
    calls = []
    _patch(avatar_cache, "cached_pixmap", lambda u: QPixmap(4, 4))
    _patch(avatar_cache, "fetch",
           lambda u, on_ready=None, on_error=None, force=False:
           calls.append((u, bool(force))) or "")
    try:
        avatar = Avatar(24)
        avatar.set_url(url)
        assert calls == []                    # 命中缓存 → 不再请求
        avatar.set_url(url, force=True)
        assert calls == [(absolute, True)]    # 强制重新下载并覆盖缓存
    finally:
        _restore_all()


def test_avatar_fetch_when_cache_missed():
    from app.widgets.images import Avatar, avatar_cache
    _qt()
    url = "https://example.invalid/avatar-miss.png"
    calls = []
    _patch(avatar_cache, "cached_pixmap", lambda u: None)
    _patch(avatar_cache, "fetch",
           lambda u, on_ready=None, on_error=None, force=False:
           calls.append((u, bool(force))) or "")
    try:
        Avatar(24).set_url(url)
        assert calls == [(constants.absolute(url), False)]
    finally:
        _restore_all()


def test_signatures_expose_force():
    from app.widgets.images import Avatar, ImageCache
    fetch = inspect.signature(ImageCache.fetch)
    assert "force" in fetch.parameters
    assert fetch.parameters["force"].default is False
    set_url = inspect.signature(Avatar.set_url)
    assert "force" in set_url.parameters
    assert set_url.parameters["force"].default is False


def test_post_detail_uses_postcache():
    from app.pages import post_detail
    assert post_detail.postcache is postcache
    source = inspect.getsource(post_detail.PostDetailPage.reload)
    assert "postcache.load" in source
    source = inspect.getsource(post_detail.PostDetailPage._on_loaded)
    assert "_save_cache" in source
