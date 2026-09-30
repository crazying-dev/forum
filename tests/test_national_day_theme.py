# -*- coding: utf-8 -*-
"""国庆节限定主题（Windows 客户端）契约测试。

规则：
  · 在现有「白天 / 夜间 / 跟随系统」基础上新增两套国庆色板；
  · 这两套主题**不支持手动切换**（设置页与托盘菜单里不可见、不可选）；
  · 国庆假期（10-01 00:00 ~ 10-07 24:00，本地时间）强制映射：
      白天 → 国庆浅色；夜间 → 国庆深色；跟随系统 → 恒为国庆浅色；
  · 配置里的 ``theme`` 仍只记录基础偏好，假期结束自动还原。

所有断言都通过打桩 :func:`app.theme.is_national_day` 固定假期状态，
因此无论在哪个日期跑都不会飘。
"""

from __future__ import annotations

from datetime import datetime

from app import config as config_mod
from app import constants, theme


class _Holiday:
    """上下文管理器：临时把「是否国庆假期」固定为给定值。"""

    def __init__(self, flag: bool) -> None:
        self.flag = flag
        self._saved = None

    def __enter__(self):
        self._saved = theme.is_national_day
        theme.is_national_day = lambda *a, **k: self.flag
        return self

    def __exit__(self, *exc):
        theme.is_national_day = self._saved
        return False


# ────────────────────── 假期窗口边界 ──────────────────────


def test_is_national_day_window_boundaries():
    assert theme.is_national_day(datetime(2026, 9, 30, 23, 59)) is False
    assert theme.is_national_day(datetime(2026, 10, 1, 0, 0)) is True
    assert theme.is_national_day(datetime(2026, 10, 1, 12, 0)) is True
    assert theme.is_national_day(datetime(2026, 10, 7, 23, 59)) is True
    # 10-07 24:00 == 10-08 00:00，闭区间右端不包含 10-08
    assert theme.is_national_day(datetime(2026, 10, 8, 0, 0)) is False
    assert theme.is_national_day(datetime(2026, 10, 8, 12, 0)) is False
    for month, day in ((1, 1), (5, 1), (6, 18), (12, 31)):
        assert theme.is_national_day(datetime(2026, month, day, 12)) is False


def test_national_window_constants():
    assert constants.NATIONAL_DAY_MONTH == 10
    assert constants.NATIONAL_DAY_FROM_DAY == 1
    assert constants.NATIONAL_DAY_TO_DAY == 7
    assert constants.THEME_NATIONAL_DAY_LIGHT == "national_day_light"
    assert constants.THEME_NATIONAL_DAY_DARK == "national_day_dark"


# ────────────────────── 假期强制映射 ──────────────────────


def test_resolve_mode_maps_to_national_during_holiday():
    with _Holiday(True):
        assert theme.resolve_mode(constants.THEME_DAY) == constants.THEME_NATIONAL_DAY_LIGHT
        assert theme.resolve_mode(constants.THEME_NIGHT) == constants.THEME_NATIONAL_DAY_DARK
        # 假期内「跟随系统」不按时间切换，恒为国庆浅色
        assert theme.resolve_mode(constants.THEME_AUTO) == constants.THEME_NATIONAL_DAY_LIGHT
        assert theme.palette(constants.THEME_AUTO) == theme.PALETTES[
            constants.THEME_NATIONAL_DAY_LIGHT]
        assert theme.palette(constants.THEME_NIGHT) == theme.PALETTES[
            constants.THEME_NATIONAL_DAY_DARK]


def test_resolve_mode_unchanged_outside_holiday():
    with _Holiday(False):
        assert theme.resolve_mode(constants.THEME_DAY) == constants.THEME_DAY
        assert theme.resolve_mode(constants.THEME_NIGHT) == constants.THEME_NIGHT
        assert theme.resolve_mode(constants.THEME_AUTO) in (constants.THEME_DAY,
                                                            constants.THEME_NIGHT)


def test_resolve_mode_idempotent_for_national_modes():
    """传入国庆主题名时原样返回（幂等），避免 apply_theme 重入时被二次映射。"""
    for holiday in (False, True):
        with _Holiday(holiday):
            for mode in (constants.THEME_NATIONAL_DAY_LIGHT,
                         constants.THEME_NATIONAL_DAY_DARK):
                assert theme.resolve_mode(mode) == mode


# ────────────────────── 色板 ──────────────────────


def test_national_palettes_complete_and_on_brand():
    light = theme.PALETTES[constants.THEME_NATIONAL_DAY_LIGHT]
    dark = theme.PALETTES[constants.THEME_NATIONAL_DAY_DARK]
    base = theme.PALETTES[constants.THEME_DAY]
    assert set(light) == set(base)
    assert set(dark) == set(base)
    # 浅色 = 中国红主色 + 暖白/米底；深色 = 亮金主色 + 暗红底
    assert light["primary"] == "#C8102E"
    assert light["bg_body"] == "#FBF3E6"
    assert dark["primary"] == "#FFD24A"
    assert dark["bg_body"] == "#3A0D12"
    # Windows 端不做透明度混合：除 shadow 外一律实色 #RRGGBB
    for name, pal in (("light", light), ("dark", dark)):
        for key, value in pal.items():
            if key == "shadow":
                continue
            assert value.startswith("#") and len(value) == 7, (name, key, value)


def test_national_qss_and_document_css_render():
    for mode in (constants.THEME_NATIONAL_DAY_LIGHT, constants.THEME_NATIONAL_DAY_DARK):
        sheet = theme.qss(mode)
        assert len(sheet) > 2000, mode
        for placeholder in ("{text_primary}", "{bg_card}", "{radius}", "{primary}",
                            "{mark_bg}", "{code_bg}"):
            assert placeholder not in sheet, (mode, placeholder)
        doc = theme.document_css(mode)
        for placeholder in ("{text_primary}", "{mark_bg}", "{code_bg}"):
            assert placeholder not in doc, (mode, placeholder)
        # 生成的样式里带上了对应色板的主色
        assert theme.PALETTES[mode]["primary"] in sheet


# ────────────────────── 不可手动切换 ──────────────────────


def test_settings_and_tray_do_not_expose_national_themes():
    from app import tray
    from app.pages import settings

    values = [value for value, _label in settings._APP_THEMES]
    assert values == [constants.THEME_DAY, constants.THEME_NIGHT, constants.THEME_AUTO], values
    tvalues = [value for value, _label in tray.THEME_ITEMS]
    assert tvalues == [constants.THEME_DAY, constants.THEME_NIGHT, constants.THEME_AUTO], tvalues
    for value in (constants.THEME_NATIONAL_DAY_LIGHT, constants.THEME_NATIONAL_DAY_DARK):
        assert value not in values, value
        assert value not in tvalues, value


def test_config_theme_only_holds_base_preference():
    """配置里的 theme 仅允许基础偏好，国庆主题不得落盘。"""
    cfg = config_mod.current()
    value = str(cfg.get("theme", constants.THEME_AUTO))
    assert value in (constants.THEME_DAY, constants.THEME_NIGHT, constants.THEME_AUTO), value
