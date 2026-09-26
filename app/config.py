# -*- coding: utf-8 -*-
"""本地配置：``~/.Cr/forum/config.json``。

* 缺省值集中放在 :data:`DEFAULTS`，读取时做深度合并，新增配置项自动补齐
* 写入使用「临时文件 + 原子替换」，避免断电/崩溃写坏配置
* 变更通过监听回调广播（不依赖 Qt，方便单测）
"""

from __future__ import annotations

import copy
import json
import os
import threading
from pathlib import Path
from typing import Any, Callable

from . import constants, paths

DEFAULTS: dict[str, Any] = {
    "version": 1,
    "theme": constants.THEME_AUTO,          # day / night / auto
    "year_mode": constants.YEAR_MODE_WUXIAN,
    "nav_mode": "side",                    # side / top
    "nav_expanded": False,
    "cursor_enabled": True,
    "cursor_variant": constants.CURSOR_VARIANT_DEFAULT,
    "check_update": True,
    "last_update_check": 0.0,
    "last_user": "",
    "pet": {
        "enabled": True,
        "screen": None,                    # 显示器序号
        "x": None,                         # 窗口左上角（屏幕坐标系）
        "y": None,
        "anchor": "bottom-right",
        "scale": 1.0,
        "opacity": 1.0,
        "passthrough": False,
        "fps": 60,
        "model": "HEI4.0",
    },
    "window": {
        "w": 1180,
        "h": 760,
        "x": None,
        "y": None,
        "maximized": False,
    },
    "world": {
        "width": constants.WORLD_WIDTH_DEFAULT,
        "collapsed": False,
    },
    "log_view": {
        "max_lines": 800,
    },
}


class Config:
    """JSON 配置容器。"""

    def __init__(self, path: Path | None = None) -> None:
        self._path = Path(path) if path else paths.config_file()
        self._data: dict[str, Any] = copy.deepcopy(DEFAULTS)
        self._lock = threading.RLock()
        self._listeners: list[Callable[[str], None]] = []
        self.load()

    # ── 基础 ──
    @property
    def path(self) -> Path:
        return self._path

    def load(self) -> None:
        with self._lock:
            data = None
            try:
                if self._path.is_file():
                    data = json.loads(self._path.read_text(encoding="utf-8"))
            except Exception:
                data = None
            merged = copy.deepcopy(DEFAULTS)
            if isinstance(data, dict):
                _deep_merge(merged, data)
            self._data = merged

    def save(self) -> bool:
        with self._lock:
            try:
                self._path.parent.mkdir(parents=True, exist_ok=True)
                tmp = self._path.with_suffix(self._path.suffix + ".tmp")
                tmp.write_text(
                    json.dumps(self._data, ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )
                os.replace(tmp, self._path)
                return True
            except Exception:
                return False

    def to_dict(self) -> dict[str, Any]:
        with self._lock:
            return copy.deepcopy(self._data)

    # ── 读取/写入（支持 'pet.enabled' 式点号路径）──
    def get(self, key: str, default: Any = None) -> Any:
        with self._lock:
            node: Any = self._data
            for part in str(key).split("."):
                if not isinstance(node, dict) or part not in node:
                    return default
                node = node[part]
            return node

    def set(self, key: str, value: Any, *, save: bool = True) -> None:
        with self._lock:
            parts = str(key).split(".")
            node = self._data
            for part in parts[:-1]:
                nxt = node.get(part)
                if not isinstance(nxt, dict):
                    nxt = {}
                    node[part] = nxt
                node = nxt
            if node.get(parts[-1]) == value:
                return
            node[parts[-1]] = value
        if save:
            self.save()
        self._notify(key)

    def update(self, values: dict[str, Any], *, save: bool = True) -> None:
        if not values:
            return
        for k, v in values.items():
            self.set(k, v, save=False)
        if save:
            self.save()
        for k in values:
            self._notify(k)

    def reset(self) -> None:
        with self._lock:
            self._data = copy.deepcopy(DEFAULTS)
        self.save()
        self._notify("*")

    # ── 变更广播 ──
    def add_listener(self, fn: Callable[[str], None]) -> None:
        if fn not in self._listeners:
            self._listeners.append(fn)

    def remove_listener(self, fn: Callable[[str], None]) -> None:
        try:
            self._listeners.remove(fn)
        except ValueError:
            pass

    def _notify(self, key: str) -> None:
        for fn in list(self._listeners):
            try:
                fn(key)
            except Exception:
                pass

    # ── 常用快捷属性 ──
    @property
    def theme(self) -> str:
        return str(self.get("theme", constants.THEME_AUTO))

    @property
    def year_mode(self) -> str:
        return str(self.get("year_mode", constants.YEAR_MODE_DEFAULT))

    @property
    def cursor_enabled(self) -> bool:
        return bool(self.get("cursor_enabled", True))

    @property
    def cursor_variant(self) -> str:
        return str(self.get("cursor_variant", constants.CURSOR_VARIANT_DEFAULT))


def _deep_merge(base: dict, extra: dict) -> None:
    for k, v in extra.items():
        if isinstance(v, dict) and isinstance(base.get(k), dict):
            _deep_merge(base[k], v)
        else:
            base[k] = v


_current: Config | None = None


def current() -> Config:
    """全局单例。"""
    global _current
    if _current is None:
        paths.ensure_dirs()
        _current = Config()
    return _current
