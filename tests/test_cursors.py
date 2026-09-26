# -*- coding: utf-8 -*-
"""鼠标指针用例：清单解析 / 帧序列 / 动画推进 / .cur 与 .ani 编码 / 写入。"""

from __future__ import annotations

import os
import struct
import tempfile

from app import constants
from app import cursors as cursors_mod

VARIANT_KEYS = ("normal", "large_dynamic", "large_static")


def _qapp():
    from PyQt6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


def test_shape_value_helper():
    from PyQt6.QtCore import Qt
    value = cursors_mod._shape_value(Qt.CursorShape.ArrowCursor)
    assert isinstance(value, int) and value >= 0
    assert cursors_mod._shape_value(None) == 0
    assert cursors_mod._shape_value(17) == 17


def test_pack_available_and_variants():
    pack = cursors_mod.CursorPack()
    assert pack.available is True
    keys = [key for key, _label in pack.variants()]
    for key in VARIANT_KEYS:
        assert key in keys, keys
    labels = dict(pack.variants())
    assert labels["normal"] == "普通"
    assert labels["large_dynamic"] == "放大·动态"
    assert labels["large_static"] == "放大·静态"


def test_pack_missing_manifest_degrades():
    pack = cursors_mod.CursorPack(os.path.join(tempfile.mkdtemp(), "nope.json"))
    assert pack.available is False
    assert pack.variants() == []
    assert pack.roles("normal") == {}


def test_every_variant_has_all_roles():
    pack = cursors_mod.CursorPack()
    expected = {role for role, _ in _ROLE_KEYS}
    for key, _label in pack.variants():
        roles = pack.roles(key)
        assert set(roles) == expected, (key, sorted(roles))


def test_role_frames_exist_and_match_manifest():
    pack = cursors_mod.CursorPack()
    checked = 0
    for key, _label in pack.variants():
        for role, cursor in pack.roles(key).items():
            paths = list(cursor.frame_paths())
            assert paths, (key, role)
            for path in paths:
                assert os.path.isfile(str(path)), path
            assert len(list(cursor.delays)) == len(list(cursor.frame_paths())) \
                or len(cursor.delays) >= 1
            assert cursor.size[0] > 0 and cursor.size[1] > 0
            hot_x, hot_y = cursor.hotspot
            assert 0 <= hot_x <= cursor.size[0] and 0 <= hot_y <= cursor.size[1]
            checked += 1
    assert checked == 45, checked


def test_animated_flag():
    pack = cursors_mod.CursorPack()
    roles = pack.roles("normal")
    assert roles["wait"].animated is True      # 忙.ani
    assert roles["arrow"].animated is True    # 正常选择.ani
    static = pack.roles("large_static")
    assert static["arrow"].animated is False


def test_frame_advance_wraps():
    pack = cursors_mod.CursorPack()
    role = pack.roles("normal")["wait"]
    total = sum(role.delays)
    assert total > 0
    first = role.frame_at(0)
    assert 0 <= first < len(list(role.frame_paths()))
    assert role.frame_at(total * 3 + 5) == role.frame_at(5 % total)


def test_scaled_hotspot():
    _qapp()
    pack = cursors_mod.CursorPack()
    role = pack.roles("normal")["arrow"]
    pixmaps = role.pixmaps()
    assert pixmaps and not pixmaps[0].isNull()
    hot_x, hot_y = role.scaled_hotspot()
    assert 0 <= hot_x <= pixmaps[0].width()
    assert 0 <= hot_y <= pixmaps[0].height()


def test_encode_cur_header():
    from PyQt6.QtGui import QColor, QPixmap
    _qapp()
    pixmap = QPixmap(8, 8)
    pixmap.fill(QColor(255, 0, 0, 255))
    blob = cursors_mod._encode_cur(pixmap, 3, 4)
    reserved, itype, count = struct.unpack_from("<HHH", blob, 0)
    assert reserved == 0 and itype == 2 and count == 1
    hot_x, hot_y = struct.unpack_from("<HH", blob, 6 + 4)
    assert (hot_x, hot_y) == (3, 4)
    assert blob[:2] == b"\x00\x00"


def test_encode_ani_riff_layout():
    from PyQt6.QtGui import QColor, QPixmap
    _qapp()
    pixmap = QPixmap(8, 8)
    pixmap.fill(QColor(0, 255, 0, 255))
    frame = cursors_mod._encode_cur(pixmap, 1, 1)
    # _encode_ani 接收的是已经编码好的 .cur 字节（按字节去重）
    blob = cursors_mod._encode_ani([frame, frame], [80, 120], "test")
    assert blob[:4] == b"RIFF" and blob[8:12] == b"ACON"
    assert b"anih" in blob and b"rate" in blob and b"seq " in blob and b"fram" in blob
    size = struct.unpack_from("<I", blob, 4)[0]
    assert size <= len(blob) - 8
    anih_at = blob.index(b"anih")
    fields = struct.unpack_from("<9I", blob, anih_at + 8)
    assert fields[0] == 36            # cbSize
    assert fields[1] == 1             # nFrames（两帧内容相同 → 去重为 1）
    assert fields[2] == 2             # nSteps


def test_write_cursor_files_to_temp_dir():
    _qapp()
    pack = cursors_mod.CursorPack()
    out = tempfile.mkdtemp()
    written, message = cursors_mod._write_cursor_files(pack, "large_static", out)
    assert written, message
    assert isinstance(written, dict) and written
    for _role, path in written.items():
        assert os.path.isfile(str(path))
        assert os.path.getsize(str(path)) > 200


def test_install_system_cursors_dry_run():
    from PyQt6.QtWidgets import QApplication
    QApplication.instance() or QApplication([])
    out = tempfile.mkdtemp()
    ok, message = cursors_mod.install_system_cursors(
        "normal", target_dir=out, dry_run=True)
    assert ok is True, message
    files = [f for f in os.listdir(out)]
    assert any(f.endswith(".cur") for f in files)
    assert any(f.endswith(".ani") for f in files)


def test_manager_install_and_variants():
    from PyQt6.QtWidgets import QApplication, QWidget
    QApplication.instance() or QApplication([])
    manager = cursors_mod.CursorManager()
    manager.install()
    widget = QWidget()
    manager.attach(widget)
    for key, _label in manager_pack_variants():
        manager.set_variant(key)
        assert manager.variant == key
    manager.set_enabled(False)
    assert manager.enabled is False
    manager.set_enabled(True)
    assert manager.enabled is True
    assert manager.cursor_for("arrow") is not None
    manager.detach(widget)
    widget.deleteLater()


def manager_pack_variants():
    return cursors_mod.CursorPack().variants()


_ROLE_KEYS = (
    ("arrow", "正常选择"), ("help", "帮助选择"), ("work", "后台运行"),
    ("wait", "忙"), ("crosshair", "精确选择"), ("text", "文本选择"),
    ("hand", "手写"), ("unavailable", "不可用"), ("sizens", "垂直调整大小"),
    ("sizewe", "水平调整大小"), ("sizenwse", "沿对角线调整大小1"),
    ("sizenesw", "沿对角线调整大小2"), ("sizeall", "移动"),
    ("uparrow", "候选"), ("link", "链接选择"),
)
