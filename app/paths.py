# -*- coding: utf-8 -*-
"""路径解析：程序目录 / 资源目录 / 用户数据目录。

数据目录固定为 ``~/.Cr/forum/``（Windows 下即 ``C:\\Users\\<你>\\.Cr\\forum``），
可用环境变量 ``CRFORUM_DATA_DIR`` 覆盖（仅用于测试）。
"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path

DATA_ROOT_NAME = ".Cr"
PRODUCT_NAME = "forum"


def app_dir() -> Path:
    """程序所在目录。

    打包后：
      * Nuitka / PyInstaller(onerdir)：``sys.executable`` 所在目录
      * PyInstaller 解包目录（_MEIPASS）也会作为回退
    开发态：仓库根目录（本文件的上一级目录）。
    """
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def resource_dir() -> Path:
    """内置资源目录（resources/）。"""
    if getattr(sys, "frozen", False):
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            cand = Path(meipass) / "resources"
            if cand.is_dir():
                return cand
        cand = Path(sys.executable).resolve().parent / "resources"
        if cand.is_dir():
            return cand
    return Path(__file__).resolve().parent.parent / "resources"


def resource(*parts: str) -> Path:
    """拼一个资源路径（不做存在性检查）。"""
    return resource_dir().joinpath(*parts)


def data_dir() -> Path:
    """用户数据目录。"""
    override = os.environ.get("CRFORUM_DATA_DIR")
    if override:
        return Path(override).expanduser()
    return Path.home() / DATA_ROOT_NAME / PRODUCT_NAME


def _sub(name: str, *extra: str) -> Path:
    return data_dir().joinpath(name, *extra)


def logs_dir() -> Path:
    return _sub("logs")


def cache_dir() -> Path:
    return _sub("cache")


def avatar_cache_dir() -> Path:
    return _sub("cache", "avatar")


def image_cache_dir() -> Path:
    return _sub("cache", "image")


def live2d_dir() -> Path:
    return _sub("Live2D")


def live2d_lpk_path() -> Path:
    return live2d_dir() / "HEI.lpk"


def live2d_model_json_path() -> Path:
    return live2d_dir() / "model.json"


def live2d_state_path() -> Path:
    return live2d_dir() / "live2d.json"


_SAFE_COMPONENT_RE = re.compile(r"[^0-9A-Za-z._-]+")


def safe_component(name: str, fallback: str = "latest") -> str:
    """把任意文本清洗成可安全用作「单层」目录 / 文件名组件。

    去掉路径分隔符与穿越（``../``、``..\\``），只保留 ``[0-9A-Za-z._-]``；
    结果为空时返回 ``fallback``。远端下发的版本号会直接进目录名，必须先清洗。
    """
    text = str(name or "").strip().replace("\\", "/").rsplit("/", 1)[-1]
    text = _SAFE_COMPONENT_RE.sub("_", text).strip(" .")
    if not text or text in (".", ".."):
        return str(fallback or "")
    return text[:64]


def update_dir(version: str = "") -> Path:
    """更新目录：``~/.Cr/forum/update/``。

    给定 ``version`` 时返回该版本的专属子目录
    （``~/.Cr/forum/update/<版本>/``），让每个版本的安装包彼此隔离，
    互不污染。
    """
    if version:
        component = safe_component(version)
        if component:
            return _sub("update", component)
    return _sub("update")


def tmp_dir() -> Path:
    return _sub("tmp")


def config_file() -> Path:
    return data_dir() / "config.json"


def account_file() -> Path:
    return data_dir() / "account.bin"


def all_dirs() -> list[Path]:
    return [
        data_dir(),
        logs_dir(),
        cache_dir(),
        avatar_cache_dir(),
        image_cache_dir(),
 live2d_dir(),
        update_dir(),
        tmp_dir(),
    ]


def ensure_dirs() -> Path:
    """建齐所有数据目录并返回数据根目录。"""
    for d in all_dirs():
        try:
            d.mkdir(parents=True, exist_ok=True)
        except OSError:
            pass
    return data_dir()
