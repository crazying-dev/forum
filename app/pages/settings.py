# -*- coding: utf-8 -*-
"""设置页（``settings`` 路由）：外观 / 鼠标 / 桌宠 / 启动与更新 / 数据与诊断 / 关于。

设计约定：

* 写配置一律落到 :func:`app.config.current`，由配置监听广播驱动外壳刷新
  （主题、导航模式在 :meth:`app.shell.Shell.on_config_changed` 里响应）
* 可选模块（系统鼠标指针 / 开机自启 / 深链 / 更新 / 桌宠）的导入全部包
  ``try/except ImportError``；模块未就绪时只给一句中文提示，页面本身绝不报错
* 运行日志订阅 :func:`app.logger.bus` 的 ``message`` 信号（信号自带主线程排队）
* 所有阻塞操作走 :meth:`Page.run`，绝不在界面线程里发请求
"""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (QCheckBox, QLabel, QLineEdit, QPlainTextEdit, QSlider,
                             QWidget)

from .. import config as config_mod
from .. import constants, logger, paths, util, yearmode
from ..widgets import (Card, CardTitle, Divider, Muted, ScrollPage, button, hbox,
                       set_active, vbox)
from .base import Page

_log = logger.get_logger("settings_page")

_APP_THEMES = ((constants.THEME_DAY, "白天"),
               (constants.THEME_NIGHT, "夜间"),
               (constants.THEME_AUTO, "跟随系统"))
_NAV_MODES = (("side", "左侧"), ("top", "顶部"))
_YEAR_MODES = ((constants.YEAR_MODE_WUXIAN, "无限年"),
               (constants.YEAR_MODE_CE, "公元年"))


class SettingsPage(Page):
    """设置页（路由 ``settings``）。"""

    ROUTE = "settings"
    TITLE = "设置"
    KEEP_ALIVE = True

    def __init__(self, shell=None, parent: QWidget | None = None) -> None:
        super().__init__(shell, parent)
        self._chip_buttons: dict[str, list] = {}
        self._year_inputs: dict[str, QLineEdit] = {}
        self._log_connected = False

        root = vbox(self, margins=(12, 12, 12, 12), spacing=10)
        header, _ = self.make_header("设置", "外观、鼠标指针、桌宠、启动更新与运行诊断")
        root.addWidget(header)
        self.scroll = ScrollPage(self, spacing=12)
        root.addWidget(self.scroll, 1)

        self._build_appearance()
        self._build_cursor()
        self._build_pet()
        self._build_startup()
        self._build_diagnostics()
        self._build_about()

        self._connect_log_bus()
        self._sync_states()

    # ── 生命周期 ──
    def on_show(self, **kwargs) -> None:
        super().on_show(**kwargs)
        self._sync_states()

    # ── 小工具 ──
    def _card(self, title: str) -> Card:
        card = Card()
        card.body.addWidget(CardTitle(title))
        self.scroll.add(card)
        return card

    @staticmethod
    def _muted(text: str) -> QLabel:
        label = Muted(text)
        label.setWordWrap(True)
        return label

    @staticmethod
    def _value_label(text: str = "") -> QLabel:
        label = Muted(text)
        label.setMinimumWidth(48)
        label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        return label

    @staticmethod
    def _slider_row(text: str, slider: QSlider, value_label: QLabel):
        row = hbox(spacing=8)
        row.addWidget(QLabel(text))
        slider.setMinimumWidth(160)
        row.addWidget(slider, 1)
        row.addWidget(value_label)
        return row

    @staticmethod
    def _set_quietly(widget, value) -> None:
        """改控件状态但不触发它自己的信号（避开写配置的回环）。"""
        if widget is None:
            return
        previous = widget.blockSignals(True)
        try:
            if isinstance(widget, QCheckBox):
                widget.setChecked(bool(value))
            elif isinstance(widget, QSlider):
                widget.setValue(int(value))
            else:
                widget.setText(str(value))
        except (RuntimeError, TypeError, ValueError):
            pass
        finally:
            widget.blockSignals(previous)

    def _chips(self, card: Card, key: str, options, handler) -> None:
        """一排单选 chip；选中态由 :meth:`_mark` 统一维护。"""
        row = hbox(spacing=6)
        buttons: list = []
        for value, label in options:
            chip_btn = button(label, "chip", lambda _=False, v=value: handler(v))
            buttons.append((value, chip_btn))
            row.addWidget(chip_btn)
        row.addStretch(1)
        card.body.addLayout(row)
        self._chip_buttons[key] = buttons

    def _mark(self, key: str, current) -> None:
        for value, chip_btn in self._chip_buttons.get(key, []):
            try:
                set_active(chip_btn, value == current)
            except RuntimeError:
                continue

    @staticmethod
    def _split(result) -> tuple[bool, str]:
        """把 ``(ok, msg)`` / ``bool`` / ``str`` 统一成 ``(ok, msg)``。"""
        if isinstance(result, tuple):
            ok = bool(result[0]) if result else False
            message = str(result[1]) if len(result) > 1 and result[1] else ""
            return ok, message
        if isinstance(result, bool):
            return result, ""
        if isinstance(result, str):
            return bool(result.strip()), result
        return bool(result), ""

    # ── 外观 ──
    def _build_appearance(self) -> None:
        card = self._card("外观")

        card.body.addWidget(self._muted("主题"))
        self._chips(card, "theme", _APP_THEMES, self._on_theme)

        card.body.addWidget(Divider())
        card.body.addWidget(self._muted("导航栏位置"))
        self._chips(card, "nav_mode", _NAV_MODES, self._on_nav_mode)

        card.body.addWidget(Divider())
        card.body.addWidget(self._muted("时间年制"))
        self._chips(card, "year_mode", _YEAR_MODES, self._on_year_mode)

        card.body.addWidget(Divider())
        card.body.addWidget(self._muted(
            "无限年换算（无限元年 = 公元 %d 年）" % constants.WUXIAN_EPOCH_CE))
        wuxian_input = QLineEdit()
        wuxian_input.setPlaceholderText("无限年，如 400")
        wuxian_input.setMaximumWidth(150)
        ce_input = QLineEdit()
        ce_input.setPlaceholderText("公元年，如 2010")
        ce_input.setMaximumWidth(150)
        self._year_inputs = {"wuxian": wuxian_input, "ce": ce_input}

        row = hbox(spacing=8)
        row.addWidget(QLabel("无限年"))
        row.addWidget(wuxian_input)
        row.addWidget(QLabel("⇄"))
        row.addWidget(QLabel("公元年"))
        row.addWidget(ce_input)
        row.addStretch(1)
        card.body.addLayout(row)

        self._year_result = self._muted("填左侧由无限年推公元年，填右侧相反。")
        card.body.addWidget(self._year_result)
        card.body.addWidget(button("换算", "ghost", lambda _=False: self._convert_year()))

    def _on_theme(self, mode: str) -> None:
        config_mod.current().set("theme", mode)
        if self.shell is not None:
            try:
                self.shell.apply_theme()
            except Exception as exc:  # noqa: BLE001
                _log.warning("刷新主题失败：%s", exc)
        self._mark("theme", mode)

    def _on_nav_mode(self, mode: str) -> None:
        # 只写配置，外壳通过自己的监听回调应用导航模式
        config_mod.current().set("nav_mode", mode)
        self._mark("nav_mode", mode)

    def _on_year_mode(self, mode: str) -> None:
        applied = yearmode.set_mode(mode)
        self._mark("year_mode", applied)
        self.toast("已切换为%s" % ("公元年" if applied == constants.YEAR_MODE_CE
                                  else "无限年"))

    def _convert_year(self) -> None:
        wuxian_text = self._year_inputs["wuxian"].text().strip()
        ce_text = self._year_inputs["ce"].text().strip()
        if wuxian_text:
            ce = yearmode.wuxian_to_ce(wuxian_text)
            if not ce:
                self._year_result.setText("请输入整数（无限年可以为负）")
                return
            self._year_result.setText("无限%s年 = 公元 %s 年" % (wuxian_text, ce))
            return
        if ce_text:
            label = yearmode.wuxian_year_label(ce_text)
            if not label:
                self._year_result.setText("请输入整数（公元年）")
                return
            self._year_result.setText("公元 %s 年 = %s" % (ce_text, label))
            return
        self._year_result.setText("请先填写无限年或公元年")

    # ── 鼠标指针 ──
    def _build_cursor(self) -> None:
        card = self._card("鼠标指针")

        self._cursor_enabled = QCheckBox("启用罗小黑鼠标指针")
        self._cursor_enabled.toggled.connect(self._on_cursor_enabled)
        card.body.addWidget(self._cursor_enabled)
        card.body.addWidget(self._muted("关闭后恢复系统自带指针样式。"))

        card.body.addWidget(Divider())
        card.body.addWidget(self._muted("指针样式"))
        self._chips(card, "cursor_variant", constants.CURSOR_VARIANTS,
                    self._on_cursor_variant)

        card.body.addWidget(Divider())
        self._cursor_scale = QSlider(Qt.Orientation.Horizontal)
        self._cursor_scale.setRange(int(constants.CURSOR_SCALE_MIN * 100),
                                    int(constants.CURSOR_SCALE_MAX * 100))
        self._cursor_scale.valueChanged.connect(self._on_cursor_scale)
        self._cursor_scale_label = self._value_label("")
        card.body.addLayout(self._slider_row("指针大小", self._cursor_scale,
                                             self._cursor_scale_label))
        card.body.addWidget(self._muted("觉得指针过大或过小都可以在这里调整。"))

        card.body.addWidget(Divider())
        self._cursor_state_label = self._muted("")
        card.body.addWidget(self._cursor_state_label)
        row = hbox(spacing=8)
        row.addWidget(button("安装为系统指针", "ghost",
                             lambda _=False: self._install_system_cursors()))
        row.addWidget(button("恢复系统默认", "ghost",
                             lambda _=False: self._restore_system_cursors()))
        row.addStretch(1)
        card.body.addLayout(row)

    def _cursor_manager(self):
        if self.shell is None:
            return None
        return getattr(self.shell, "cursor_manager", None)

    @staticmethod
    def _cursor_api():
        """系统指针相关函数（模块未就绪时返回 None）。"""
        try:
            from ..cursors import (install_system_cursors, restore_system_cursors,
                                   system_cursors_installed)
        except ImportError:
            return None
        return install_system_cursors, restore_system_cursors, system_cursors_installed

    def _on_cursor_enabled(self, checked: bool) -> None:
        config_mod.current().set("cursor_enabled", bool(checked))
        manager = self._cursor_manager()
        setter = getattr(manager, "set_enabled", None)
        if callable(setter):
            try:
                setter(bool(checked))
            except Exception as exc:  # noqa: BLE001
                _log.warning("应用指针开关失败：%s", exc)

    def _on_cursor_variant(self, key: str) -> None:
        config_mod.current().set("cursor_variant", key)
        manager = self._cursor_manager()
        setter = getattr(manager, "set_variant", None)
        if callable(setter):
            try:
                setter(key)
            except Exception as exc:  # noqa: BLE001
                _log.warning("切换指针样式失败：%s", exc)
        self._mark("cursor_variant", key)

    def _on_cursor_scale(self, value: int) -> None:
        scale = round(int(value) / 100.0, 2)
        config_mod.current().set("cursor_scale", scale)
        manager = self._cursor_manager()
        setter = getattr(manager, "set_scale", None)
        if callable(setter):
            try:
                setter(scale)
            except Exception as exc:  # noqa: BLE001
                _log.warning("调整指针大小失败：%s", exc)
        self._update_cursor_scale_label()

    def _update_cursor_scale_label(self) -> None:
        slider = getattr(self, "_cursor_scale", None)
        label = getattr(self, "_cursor_scale_label", None)
        if slider is None or label is None:
            return
        try:
            label.setText("%d%%" % slider.value())
        except RuntimeError:
            return

    def _current_variant(self) -> str:
        try:
            return str(config_mod.current().get(
                "cursor_variant", constants.CURSOR_VARIANT_DEFAULT)
                or constants.CURSOR_VARIANT_DEFAULT)
        except Exception:  # noqa: BLE001
            return constants.CURSOR_VARIANT_DEFAULT

    def _install_system_cursors(self) -> None:
        api = self._cursor_api()
        if api is None:
            self.toast("鼠标指针模块尚未就绪")
            return
        variant = self._current_variant()
        if not self.confirm(
                "安装为系统鼠标指针",
                "将把「罗小黑战记」指针写入系统指针目录，并修改当前用户的指针方案。"
                "随时可以在本页点「恢复系统默认」还原。",
                ok_text="安装"):
            return
        self.run(lambda: api[0](variant),
                 lambda result: self._after_cursor(result, "已安装为系统鼠标指针"),
                 lambda message: self._after_cursor_failure(message),
                 label="安装系统指针")

    def _restore_system_cursors(self) -> None:
        api = self._cursor_api()
        if api is None:
            self.toast("鼠标指针模块尚未就绪")
            return
        if not self.confirm(
                "恢复系统默认指针",
                "将把当前用户的鼠标指针方案恢复为 Windows 默认，并移除已写入的指针文件。",
                ok_text="恢复", danger=True):
            return
        self.run(api[1],
                 lambda result: self._after_cursor(result, "已恢复系统默认鼠标指针"),
                 lambda message: self._after_cursor_failure(message),
                 label="恢复系统指针")

    def _after_cursor(self, result, ok_text: str) -> None:
        ok, message = self._split(result)
        self._refresh_cursor_state()
        self.toast(message or (ok_text if ok else "操作失败"))

    def _after_cursor_failure(self, message: str) -> None:
        self._refresh_cursor_state()
        self.toast(message)

    def _refresh_cursor_state(self) -> None:
        label = getattr(self, "_cursor_state_label", None)
        if label is None:
            return
        api = self._cursor_api()
        if api is None:
            text = "系统指针功能不可用（模块未就绪）"
        else:
            try:
                installed = bool(api[2]())
            except Exception:  # noqa: BLE001
                installed = False
            text = ("当前已安装为系统鼠标指针。" if installed
                    else "当前使用客户端内置指针，未修改系统方案。")
        try:
            label.setText(text)
        except RuntimeError:
            return

    # ── 桌宠 ──
    def _build_pet(self) -> None:
        card = self._card("桌宠")

        self._pet_enabled = QCheckBox("显示桌宠")
        self._pet_enabled.toggled.connect(self._on_pet_enabled)
        card.body.addWidget(self._pet_enabled)

        self._pet_passthrough = QCheckBox("鼠标穿透（不挡住点击）")
        self._pet_passthrough.toggled.connect(self._on_pet_passthrough)
        card.body.addWidget(self._pet_passthrough)

        self._pet_track = QCheckBox("视线跟随鼠标（窗口外也生效）")
        self._pet_track.toggled.connect(self._on_pet_track)
        card.body.addWidget(self._pet_track)

        card.body.addWidget(Divider())
        card.body.addWidget(self._muted("模型版本"))
        self._chips(card, "pet_model", constants.live2d_model_choices(),
                    self._on_pet_model)
        card.body.addWidget(self._muted(
            "切换后会自动下载并缓存对应模型；不同版本的模型动作、表情略有差异。"))

        card.body.addWidget(Divider())
        self._pet_opacity = QSlider(Qt.Orientation.Horizontal)
        self._pet_opacity.setRange(20, 100)
        self._pet_opacity.valueChanged.connect(self._on_pet_opacity)
        self._pet_opacity_label = self._value_label("")
        card.body.addLayout(self._slider_row("不透明度", self._pet_opacity,
                                             self._pet_opacity_label))

        self._pet_scale = QSlider(Qt.Orientation.Horizontal)
        self._pet_scale.setRange(30, 200)
        self._pet_scale.valueChanged.connect(self._on_pet_scale)
        self._pet_scale_label = self._value_label("")
        card.body.addLayout(self._slider_row("缩放", self._pet_scale,
                                             self._pet_scale_label))

        card.body.addWidget(Divider())
        self._pet_note = self._muted("")
        card.body.addWidget(self._pet_note)

        row = hbox(spacing=8)
        row.addWidget(button("重新下载模型", "ghost",
                             lambda _=False: self._pet_action(
                                 ("redownload_model", "download_model",
                                  "reload_model"), "已开始重新下载模型")))
        row.addWidget(button("清理缓存", "ghost",
                             lambda _=False: self._pet_action(
                                 ("clear_cache",), "已清理模型缓存")))
        row.addStretch(1)
        card.body.addLayout(row)

    def _pet_controller(self):
        if self.shell is None:
            return None
        return getattr(self.shell, "pet_controller", None)

    def _pet_apply(self, **values) -> None:
        cfg = config_mod.current()
        for key, value in values.items():
            cfg.set("pet." + key, value)
        controller = self._pet_controller()
        applier = getattr(controller, "apply_config", None)
        if callable(applier):
            try:
                applier()
            except Exception as exc:  # noqa: BLE001
                _log.warning("应用桌宠配置失败：%s", exc)
        self._update_pet_note()

    def _on_pet_enabled(self, checked: bool) -> None:
        self._pet_apply(enabled=bool(checked))

    def _on_pet_passthrough(self, checked: bool) -> None:
        self._pet_apply(passthrough=bool(checked))

    def _on_pet_track(self, checked: bool) -> None:
        self._pet_apply(track=bool(checked))

    def _on_pet_model(self, key: str) -> None:
        spec = constants.live2d_model(key)
        config_mod.current().set("pet.model", spec["key"])
        controller = self._pet_controller()
        setter = getattr(controller, "set_model_version", None)
        if callable(setter):
            try:
                setter(spec["key"])
            except Exception as exc:  # noqa: BLE001
                _log.warning("切换模型版本失败：%s", exc)
        self._mark("pet_model", spec["key"])
        self.toast("已切换为模型版本 %s" % spec["label"])

    def _on_pet_opacity(self, value: int) -> None:
        self._pet_apply(opacity=round(int(value) / 100.0, 2))
        self._update_pet_labels()

    def _on_pet_scale(self, value: int) -> None:
        self._pet_apply(scale=round(int(value) / 100.0, 2))
        self._update_pet_labels()

    def _update_pet_labels(self) -> None:
        for slider, label, suffix in (
                (getattr(self, "_pet_opacity", None),
                 getattr(self, "_pet_opacity_label", None), "%"),
                (getattr(self, "_pet_scale", None),
                 getattr(self, "_pet_scale_label", None), "%")):
            if slider is None or label is None:
                continue
            try:
                label.setText("%d%s" % (slider.value(), suffix))
            except RuntimeError:
                continue

    def _update_pet_note(self) -> None:
        label = getattr(self, "_pet_note", None)
        if label is None:
            return
        try:
            if self._pet_controller() is None:
                text = "桌宠模块未启用（未安装 Live2D 运行库时不可用）。"
            else:
                text = "修改会立即生效；模型文件缺失时可点「重新下载模型」。"
            label.setText(text)
        except RuntimeError:
            return

    def _pet_action(self, names, ok_text: str) -> None:
        controller = self._pet_controller()
        for name in names:
            action = getattr(controller, name, None)
            if callable(action):
                self._run_quietly(action, ok_text)
                return
        fallback = self._provider_action(names)
        if fallback is not None:
            self._run_quietly(fallback, ok_text)
            return
        self.toast("桌宠模块未启用")

    @staticmethod
    def _provider_action(names):
        """没有控制器时，直接拿 :class:`Live2DProvider` 当备胎。"""
        try:
            from ..live2d import Live2DProvider
        except ImportError:
            return None
        mapping = {
            "redownload_model": lambda: Live2DProvider().ensure(force=True),
            "download_model": lambda: Live2DProvider().ensure(force=True),
            "reload_model": lambda: Live2DProvider().ensure(),
            "clear_cache": lambda: Live2DProvider().clear_cache(),
        }
        for name in names:
            action = mapping.get(name)
            if action is not None:
                return action
        return None

    def _run_quietly(self, fn, ok_text: str) -> None:
        """阻塞操作放后台线程跑，结果只用一个 toast 汇报。"""
        self.run(fn,
                 lambda _result=None, text=ok_text: self.toast(text),
                 lambda message: self.toast(message),
                 label="桌宠操作")

    # ── 启动与更新 ──
    def _build_startup(self) -> None:
        card = self._card("启动与更新")

        self._autostart_box = QCheckBox("开机自动启动")
        self._autostart_box.toggled.connect(self._on_autostart)
        card.body.addWidget(self._autostart_box)
        self._autostart_note = self._muted("")
        card.body.addWidget(self._autostart_note)

        card.body.addWidget(Divider())
        self._scheme_box = QCheckBox("注册 %s 链接" % constants.URI_SCHEME_DISPLAY)
        self._scheme_box.toggled.connect(self._on_scheme)
        card.body.addWidget(self._scheme_box)
        card.body.addWidget(self._muted("注册后可从浏览器直接打开论坛链接。"))

        card.body.addWidget(Divider())
        row = hbox(spacing=8)
        row.addWidget(button("检查更新", "ghost",
                             lambda _=False: self._check_update()))
        self._version_label = self._muted("当前版本 v%s" % constants.APP_VERSION)
        row.addWidget(self._version_label)
        row.addWidget(button("打开下载页", "ghost",
                             lambda _=False: self.go("download")))
        row.addStretch(1)
        card.body.addLayout(row)

    @staticmethod
    def _autostart_api():
        try:
            from .. import autostart
        except ImportError:
            return None
        enable = getattr(autostart, "enable", None)
        disable = getattr(autostart, "disable", None)
        checker = getattr(autostart, "is_enabled", None)
        if not callable(enable) or not callable(disable):
            return None
        return enable, disable, checker

    def _on_autostart(self, checked: bool) -> None:
        api = self._autostart_api()
        if api is None:
            self.toast("开机自启模块尚未就绪")
            self._sync_autostart()
            return
        action = api[0] if checked else api[1]
        self.run(action,
                 lambda result: self._after_autostart(result),
                 lambda message: self._after_autostart_failure(message),
                 label="开机自启")

    def _after_autostart(self, result) -> None:
        ok, message = self._split(result)
        self._sync_autostart()
        self.toast(message or ("已开启开机自启" if ok else "操作失败"))

    def _after_autostart_failure(self, message: str) -> None:
        self._sync_autostart()
        self.toast(message)

    def _sync_autostart(self) -> None:
        box = getattr(self, "_autostart_box", None)
        note = getattr(self, "_autostart_note", None)
        if box is None:
            return
        api = self._autostart_api()
        if api is None:
            self._set_quietly(box, False)
            try:
                box.setEnabled(False)
            except RuntimeError:
                return
            if note is not None:
                try:
                    note.setText("开机自启模块尚未就绪。")
                except RuntimeError:
                    pass
            return
        try:
            box.setEnabled(True)
        except RuntimeError:
            return
        enabled = False
        if callable(api[2]):
            try:
                enabled = bool(api[2]())
            except Exception:  # noqa: BLE001
                enabled = False
        self._set_quietly(box, enabled)
        if note is not None:
            try:
                note.setText("已开启：登录 Windows 后自动启动。" if enabled
                             else "关闭：需要手动启动本客户端。")
            except RuntimeError:
                pass

    def _on_scheme(self, checked: bool) -> None:
        try:
            from ..deeplink import register_scheme, unregister_scheme
        except ImportError:
            self.toast("深链模块尚未就绪")
            self._sync_scheme()
            return
        action = register_scheme if checked else unregister_scheme
        self.run(action,
                 lambda result: self._after_scheme(result),
                 lambda message: self._after_scheme_failure(message),
                 label="注册链接协议")

    def _after_scheme(self, result) -> None:
        ok, message = self._split(result)
        self._sync_scheme()
        self.toast(message or ("已注册链接协议" if ok else "操作失败"))

    def _after_scheme_failure(self, message: str) -> None:
        self._sync_scheme()
        self.toast(message)

    def _sync_scheme(self) -> None:
        box = getattr(self, "_scheme_box", None)
        if box is None:
            return
        try:
            from ..deeplink import is_registered
        except ImportError:
            self._set_quietly(box, False)
            try:
                box.setEnabled(False)
            except RuntimeError:
                pass
            return
        registered = False
        try:
            registered = bool(is_registered())
        except Exception:  # noqa: BLE001
            registered = False
        self._set_quietly(box, registered)

    def _check_update(self) -> None:
        """检查更新：发现新版本时弹窗询问是否下载（三处入口共用交互）。"""
        try:
            from ..widgets import update as update_ui
        except Exception as exc:  # noqa: BLE001
            _log.warning("加载更新组件失败：%s", exc)
            self.toast("更新模块尚未就绪")
            return
        update_ui.check_and_prompt(self, on_status=self.toast)

    # ── 数据与诊断 ──
    def _build_diagnostics(self) -> None:
        card = self._card("数据与诊断")

        row = hbox(spacing=8)
        row.addWidget(button("打开数据目录", "ghost",
                             lambda _=False: self._open_data_dir()))
        row.addWidget(button("打开今日日志", "ghost",
                             lambda _=False: self._open_log_file()))
        row.addStretch(1)
        card.body.addLayout(row)
        card.body.addWidget(self._muted("数据目录：%s" % paths.data_dir()))

        card.body.addWidget(Divider())
        card.body.addWidget(self._muted("运行日志"))

        self._log_view = QPlainTextEdit()
        self._log_view.setReadOnly(True)
        self._log_view.setMaximumBlockCount(self._log_limit())
        self._log_view.setPlaceholderText("运行日志会实时显示在这里。")
        self._log_view.setMinimumHeight(180)
        card.body.addWidget(self._log_view)

        row = hbox(spacing=8)
        row.addWidget(button("清空显示", "ghost",
                             lambda _=False: self._log_view.clear()))
        row.addWidget(button("反馈 Bug", "ghost",
                             lambda _=False: self.bug_report()))
        row.addStretch(1)
        card.body.addLayout(row)

    def _open_data_dir(self) -> None:
        try:
            paths.ensure_dirs()
        except Exception as exc:  # noqa: BLE001
            _log.warning("创建数据目录失败：%s", exc)
        if not util.reveal_in_explorer(str(paths.data_dir())):
            self.toast("打开数据目录失败")

    def _open_log_file(self) -> None:
        try:
            target = logger.current_log_file()
        except Exception as exc:  # noqa: BLE001
            _log.warning("定位日志文件失败：%s", exc)
            self.toast("打开日志失败")
            return
        if not util.reveal_in_explorer(str(target)):
            self.toast("打开日志失败")

    @staticmethod
    def _log_limit() -> int:
        try:
            value = int(config_mod.current().get("log_view.max_lines", 800))
        except (TypeError, ValueError):
            value = 800
        return max(100, value)

    def _connect_log_bus(self) -> None:
        if self._log_connected:
            return
        try:
            logger.bus().message.connect(self._on_log)
        except Exception as exc:  # noqa: BLE001
            _log.warning("订阅运行日志失败：%s", exc)
            return
        self._log_connected = True

    def _on_log(self, level: str, text: str) -> None:
        view = getattr(self, "_log_view", None)
        if view is None:
            return
        try:
            bar = view.verticalScrollBar()
            follow = bar.maximum() - bar.value() <= 24
            view.appendHtml('<span style="color:%s">%s</span>'
                            % (logger.level_color(level), util.html_escape(text)))
            if follow:
                bar.setValue(bar.maximum())
        except RuntimeError:
            return

    # ── 关于 ──
    def _build_about(self) -> None:
        card = self._card("关于")
        card.body.addWidget(self._muted("%s · v%s"
                                        % (constants.APP_NAME_EN,
                                           constants.APP_VERSION)))
        card.body.addWidget(Divider())
        card.body.addWidget(self._muted("后端地址：已内置（不可修改）"))
        card.body.addWidget(self._muted("数据目录：%s" % paths.data_dir()))
        card.body.addWidget(self._muted(
            "界面基于 PyQt6 构建（GPL v3）。本客户端为《罗小黑战记》粉丝同人项目，"
            "仅供学习与交流。"))

        row = hbox(spacing=8)
        row.addWidget(button("隐私政策", "ghost",
                             lambda _=False: self.go("privacy")))
        row.addWidget(button("会馆列表", "ghost",
                             lambda _=False: self.go("huiguan")))
        row.addWidget(button("打开 WIKI", "ghost",
                             lambda _=False: self.go("wiki")))
        row.addWidget(button("下载客户端", "ghost",
                             lambda _=False: self.go("download")))
        row.addStretch(1)
        card.body.addLayout(row)

    # ── 状态同步 ──
    def _sync_states(self) -> None:
        cfg = config_mod.current()
        self._mark("theme", cfg.get("theme", constants.THEME_AUTO))
        self._mark("nav_mode", cfg.get("nav_mode", "side"))
        try:
            mode = yearmode.get_mode()
        except Exception:  # noqa: BLE001
            mode = constants.YEAR_MODE_DEFAULT
        self._mark("year_mode", mode)
        self._mark("cursor_variant",
                   cfg.get("cursor_variant", constants.CURSOR_VARIANT_DEFAULT))
        try:
            model_key = constants.live2d_model(
                cfg.get("pet.model", constants.LIVE2D_MODEL_DEFAULT))["key"]
        except Exception:  # noqa: BLE001
            model_key = constants.LIVE2D_MODEL_DEFAULT
        self._mark("pet_model", model_key)

        self._set_quietly(getattr(self, "_cursor_enabled", None),
                          cfg.get("cursor_enabled", True))
        self._set_quietly(getattr(self, "_pet_enabled", None),
                          cfg.get("pet.enabled", True))
        self._set_quietly(getattr(self, "_pet_passthrough", None),
                          cfg.get("pet.passthrough", False))
        self._set_quietly(getattr(self, "_pet_opacity", None),
                          self._percent(cfg.get("pet.opacity", 1.0), 100, 20, 100))
        self._set_quietly(getattr(self, "_pet_scale", None),
                          self._percent(cfg.get("pet.scale", 1.0), 100, 30, 200))
        self._set_quietly(getattr(self, "_pet_track", None),
                          cfg.get("pet.track", True))
        self._set_quietly(getattr(self, "_cursor_scale", None),
                          self._percent(cfg.get("cursor_scale", 1.0), 100,
                                        int(constants.CURSOR_SCALE_MIN * 100),
                                        int(constants.CURSOR_SCALE_MAX * 100)))

        self._refresh_cursor_state()
        self._sync_autostart()
        self._sync_scheme()
        self._update_pet_note()
        self._update_pet_labels()
        self._update_cursor_scale_label()

    @staticmethod
    def _percent(value, factor: int, low: int, high: int) -> int:
        """把 0.85 这类比率换算成滑块用的整数百分比（并夹在区间内）。"""
        try:
            number = int(round(float(value) * factor))
        except (TypeError, ValueError):
            number = factor
        return max(low, min(high, number))
