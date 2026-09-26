# -*- coding: utf-8 -*-
r"""开机自启：写 ``HKCU\Software\Microsoft\Windows\CurrentVersion\Run``。

* 仅支持 Windows；键值名为 ``CrForum``，值为 ``"<exe>" --minimized``
* 打包态（``sys.frozen``）用 ``sys.executable``；开发态不写注册表
* 所有函数都不抛异常，失败原因以中文提示返回
"""

from __future__ import annotations

import sys

from . import logger

_log = logger.get_logger("autostart")

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
VALUE_NAME = "CrForum"
ARGUMENTS = "--minimized"

DEV_NOT_SUPPORTED = "开发态不支持开机自启，请用打包后的程序设置"
PLATFORM_NOT_SUPPORTED = "当前系统不支持开机自启（仅 Windows）"


def is_supported() -> bool:
    """是否支持开机自启（仅 Windows）。"""
    try:
        return sys.platform.startswith("win")
    except Exception:
        return False


def _frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def _registry():
    """惰性导入 winreg（非 Windows 上不存在）。"""
    import winreg  # noqa: PLC0415
    return winreg


def _command(exe: str) -> str:
    """注册表里的启动命令。"""
    return '"%s" %s' % (exe, ARGUMENTS)


def is_enabled() -> bool:
    """注册表里是否已有自启项。"""
    if not is_supported():
        return False
    try:
        winreg = _registry()
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
            value, _kind = winreg.QueryValueEx(key, VALUE_NAME)
        return bool(str(value or "").strip())
    except FileNotFoundError:
        return False
    except OSError:
        return False
    except Exception as exc:  # noqa: BLE001
        _log.debug("读取开机自启失败：%s", exc)
        return False


def enable(exe: str | None = None) -> tuple[bool, str]:
    """开启开机自启，返回 ``(是否成功, 中文提示)``。"""
    if not is_supported():
        return (False, PLATFORM_NOT_SUPPORTED)

    if exe:
        target = str(exe)
    elif _frozen():
        target = str(sys.executable)
    else:
        return (False, DEV_NOT_SUPPORTED)

    if not target.strip():
        return (False, "没有可用的程序路径，设置开机自启失败")

    try:
        winreg = _registry()
        with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, RUN_KEY, 0,
                                winreg.KEY_SET_VALUE) as key:
            winreg.SetValueEx(key, VALUE_NAME, 0, winreg.REG_SZ, _command(target))
        _log.info("已开启开机自启：%s", target)
        return (True, "已开启开机自启")
    except Exception as exc:  # noqa: BLE001
        _log.warning("开启开机自启失败：%s", exc)
        return (False, "开启开机自启失败：%s" % exc)


def disable() -> tuple[bool, str]:
    """关闭开机自启，返回 ``(是否成功, 中文提示)``。"""
    if not is_supported():
        return (False, PLATFORM_NOT_SUPPORTED)
    try:
        winreg = _registry()
        with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, RUN_KEY, 0,
                                winreg.KEY_SET_VALUE) as key:
            try:
                winreg.DeleteValue(key, VALUE_NAME)
            except FileNotFoundError:
                pass  # 本来就没设置，视为关闭成功
        _log.info("已关闭开机自启")
        return (True, "已关闭开机自启")
    except Exception as exc:  # noqa: BLE001
        _log.warning("关闭开机自启失败：%s", exc)
        return (False, "关闭开机自启失败：%s" % exc)


def status() -> tuple[bool, str]:
    """返回 ``(是否已开启, 中文说明)``。"""
    if not is_supported():
        return (False, PLATFORM_NOT_SUPPORTED)
    try:
        if is_enabled():
            return (True, "开机自启已开启")
        if not _frozen():
            return (False, DEV_NOT_SUPPORTED)
        return (False, "开机自启未开启")
    except Exception as exc:  # noqa: BLE001
        _log.warning("读取开机自启状态失败：%s", exc)
        return (False, "读取开机自启状态失败：%s" % exc)
