# -*- coding: utf-8 -*-
"""Live2D 用例：LPK 工具 / 动作统计 / 缓存解包 / provider 路径。"""

from __future__ import annotations

import json
import os
import shutil
import tempfile

from app import paths
from app.live2d import motion_spec, pack_utils
from app.live2d.provider import LPKError, Live2DProvider

# 开发期实测时下载/解包出的缓存（存在则复用，不存在就跳过相关用例）
CACHE_SRC = os.path.join(tempfile.gettempdir(), "crforum_live2d_test", "Live2D")
ONLINE = os.environ.get("CRFORUM_ONLINE") == "1"


# ────────────────────── pack_utils ──────────────────────


def test_hashed_filename_is_md5_of_utf8():
    import hashlib
    for text in ("config.mlve", "模型.model3.json", "FileReferences_Moc_0.moc3"):
        expect = hashlib.md5(text.encode("utf-8")).hexdigest()
        assert pack_utils.hashed_filename(text) == expect
        assert len(pack_utils.hashed_filename(text)) == 32


def test_genkey_known_values():
    assert pack_utils.genkey("") == 0
    assert pack_utils.genkey("A") == 65
    assert isinstance(pack_utils.genkey("HEI4.0"), int)
    assert 0 <= pack_utils.genkey("HEI4.0") <= 0xFFFFFFFF


def test_decrypt_is_involution():
    key = pack_utils.genkey("HEI4.0")
    data = bytes(range(256)) * 5
    once = pack_utils.decrypt(key, data)
    assert len(once) == len(data)
    assert once != data
    assert pack_utils.decrypt(key, once) == data


def test_match_rule_and_is_encrypted():
    assert pack_utils.match_rule.match("a" * 32 + ".bin3") is not None
    assert pack_utils.match_rule.match("a" * 32 + ".bin") is not None
    assert pack_utils.match_rule.match("short.bin3") is None
    assert pack_utils.is_encrypted_file("b" * 32 + ".bin3") is True
    assert pack_utils.is_encrypted_file("model0.json") is False


def test_guess_type_detects_moc3():
    kind = pack_utils.guess_type(b"MOC3" + b"\x00" * 32)
    assert kind
    assert "moc" in str(kind).lower()


# ────────────────────── 动作统计 ──────────────────────


def test_recount_motion_matches_algorithm():
    motion = {"Curves": [
        {"Target": "ParamAngleX", "Id": "ParamAngleX",
         "Segments": [0.0, 0.0, 0, 0.0, 1.0, 1, 0.5, 0.0, 0.0, 0.0, 0.0, 1.0]},
        {"Target": "ParamAngleY", "Id": "ParamAngleY",
         "Segments": [0.0, 0.0, 2, 0.0, 1.0, 0.0, 0.0, 1.0]},
    ]}
    curve, segment, point = motion_spec.recount_motion(motion)
    assert curve == 2
    assert segment == 2 + 2
    assert point == (1 + 1 + 3) + (1 + 1 + 1)


def test_recount_motion_rejects_unknown_identifier():
    motion = {"Curves": [{"Segments": [0.0, 0.0, 9, 0.0, 1.0]}]}
    try:
        motion_spec.recount_motion(motion)
    except ValueError:
        return
    raise AssertionError("未知 segment 标识符应当报 ValueError")


# ────────────────────── provider ──────────────────────


def test_provider_paths_under_data_dir():
    provider = Live2DProvider()
    root = str(provider.root_dir)
    assert root.startswith(os.environ["CRFORUM_DATA_DIR"]), root
    assert str(provider.lpk_path).endswith("HEI.lpk")
    assert str(provider.model_json).endswith(".model3.json")
    assert str(provider.pointer_path).endswith("model.json")
    assert provider.model_json.parent == provider.model_dir


def test_provider_data_dir_override():
    override = tempfile.mkdtemp()
    provider = Live2DProvider(data_dir=override)
    assert str(provider.root_dir) == os.path.join(override, "Live2D")
    assert str(provider.lpk_path) == os.path.join(override, "Live2D", "HEI.lpk")


def test_provider_not_ready_on_empty_dir():
    provider = Live2DProvider(data_dir=tempfile.mkdtemp())
    assert provider.is_ready() is False
    info = provider.info()
    assert info["model"] is False and info["lpk"] is False


def test_provider_clear_cache():
    folder = tempfile.mkdtemp()
    provider = Live2DProvider(data_dir=folder)
    provider.root_dir.mkdir(parents=True, exist_ok=True)
    provider.lpk_path.write_bytes(b"fake")
    provider.pointer_path.write_text("{}", encoding="utf-8")
    provider.clear_cache(keep_lpk=False)
    assert not provider.lpk_path.exists()
    assert not provider.pointer_path.exists()


def test_cached_model_is_self_consistent():
    """有缓存时：验证 model3.json 里引用的资源真的存在（引用完整性）。"""
    if not os.path.isdir(CACHE_SRC):
        return
    target = paths.live2d_dir()
    shutil.copytree(CACHE_SRC, target, dirs_exist_ok=True)
    provider = Live2DProvider()
    assert provider.is_ready() is True
    model_path = provider.ensure()
    assert os.path.isfile(str(model_path))
    with open(str(model_path), encoding="utf-8") as fh:
        payload = json.load(fh)
    refs = payload.get("FileReferences") or {}
    base = os.path.dirname(str(model_path))
    moc = refs.get("Moc")
    assert moc and os.path.isfile(os.path.join(base, moc))
    textures = refs.get("Textures") or []
    assert textures
    for item in textures:
        name = item if isinstance(item, str) else item.get("File")
        assert os.path.isfile(os.path.join(base, name)), name
    motions = refs.get("Motions") or {}
    assert motions, "模型应当带动作组"
    count = 0
    for group in motions.values():
        for entry in group:
            name = entry.get("File")
            if not name:
                continue
            path = os.path.join(base, name)
            assert os.path.isfile(path), path
            with open(path, encoding="utf-8") as fh:
                mj = json.load(fh)
            assert "Curves" in mj
            assert "Meta" in mj and "CurveCount" in mj["Meta"]
            count += 1
    assert count >= 10, count
    assert payload.get("HitAreas"), "模型应当带 HitAreas"


def test_widget_module_importable():
    from app.live2d import widget
    assert callable(widget.load_live2d)
    assert isinstance(widget.live2d_error(), str)


# ────────────────────── 桌宠窗口尺寸 / 视线跟随 ──────────────────────


def test_pet_default_size_is_compact():
    """回归：默认尺寸曾为 (380, 560)，用户反馈“桌宠过大”。"""
    from app.live2d import pet as pet_mod
    assert pet_mod.DEFAULT_SIZE == (272, 400)
    assert pet_mod.MIN_SCALE <= 0.3


def test_scale_floor_clamps():
    from app.live2d import pet as pet_mod
    assert pet_mod._scale_floor(1.0) == 1.0
    assert pet_mod._scale_floor(0.01) == pet_mod.MIN_SCALE
    assert pet_mod._scale_floor("bad") == 1.0
    assert pet_mod._scale_floor(None) == 1.0


def test_pet_window_size_follows_scale():
    from PyQt6.QtWidgets import QApplication, QWidget
    QApplication.instance() or QApplication([])
    from app.config import Config
    from app.live2d import pet as pet_mod
    cfg = Config(path=os.path.join(tempfile.mkdtemp(), "config.json"))
    window = pet_mod.PetWindow()
    try:
        cfg.set("pet.scale", 1.0)
        window.restore_position(cfg)
        assert (window.width(), window.height()) == pet_mod.DEFAULT_SIZE
        cfg.set("pet.scale", 2.0)
        window.restore_position(cfg)
        assert (window.width(), window.height()) == (
            pet_mod.DEFAULT_SIZE[0] * 2, pet_mod.DEFAULT_SIZE[1] * 2)
    finally:
        window.deleteLater()
        assert isinstance(window, QWidget)


def test_pet_window_track_flag_and_timer():
    from PyQt6.QtWidgets import QApplication
    QApplication.instance() or QApplication([])
    from app.config import Config
    from app.live2d import pet as pet_mod
    cfg = Config(path=os.path.join(tempfile.mkdtemp(), "config.json"))
    window = pet_mod.PetWindow()
    try:
        cfg.set("pet.track", False)
        window.apply_config(cfg)
        assert window._track is False
        assert window._track_timer.isActive() is False
        cfg.set("pet.track", True)
        window.apply_config(cfg)
        assert window._track is True
    finally:
        window.deleteLater()


def test_widget_track_screen_pos_is_safe_without_model():
    """没有模型时 track_screen_pos() 不得抛异常。"""
    from PyQt6.QtWidgets import QApplication
    QApplication.instance() or QApplication([])
    from app.live2d.widget import Live2DWidget
    view = Live2DWidget(transparent=True)
    try:
        assert view.is_loaded() is False
        view.track_screen_pos()
    finally:
        view.deleteLater()


def test_online_ensure_downloads_and_caches():
    if not ONLINE:
        return
    provider = Live2DProvider()
    path = provider.ensure()
    assert os.path.isfile(str(path))
    size = provider.lpk_path.stat().st_size
    assert size > 1_000_000, size
    assert provider.info()["model"] is True
    again = provider.ensure()
    assert str(again) == str(path)
