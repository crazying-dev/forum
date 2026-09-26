# -*- coding: utf-8 -*-
"""日志：按天写文件 + Qt 信号双通道。

* 文件：``~/.Cr/forum/logs/forum_YYYYMMDD.log``（保留 14 天）
* 界面：通过 :class:`LogBus` 的信号广播，设置页的「运行日志」面板订阅它
"""

from __future__ import annotations

import logging
import os
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

from PyQt6.QtCore import QObject, pyqtSignal

from . import paths

ROOT_NAME = "crforum"
LOG_FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
DATE_FORMAT = "%H:%M:%S"
KEEP_DAYS = 14

LEVEL_COLORS = {
    "DEBUG": "#89b4fa",
    "INFO": "#a6e3a1",
    "WARNING": "#f9e2af",
    "ERROR": "#f38ba8",
    "CRITICAL": "#f38ba8",
}


def level_color(level: str) -> str:
    return LEVEL_COLORS.get(str(level or "").upper(), "#cdd6f4")


class LogBus(QObject):
    """把日志以信号形式广播给界面（工作线程不得直接碰控件）。"""

    message = pyqtSignal(str, str)  # (level, text)


_bus: LogBus | None = None
_initialized = False
_lock = threading.Lock()


def bus() -> LogBus:
    global _bus
    if _bus is None:
        _bus = LogBus()
    return _bus


class _DailyFileHandler(logging.Handler):
    """按天切文件；跨天自动换文件。"""

    def __init__(self, folder: Path) -> None:
        super().__init__()
        self._folder = Path(folder)
        self._io_lock = threading.Lock()
        self._day = ""
        self._stream = None

    def _stream_for_today(self):
        day = datetime.now().strftime("%Y%m%d")
        if day != self._day or self._stream is None:
            self._close()
            try:
                self._folder.mkdir(parents=True, exist_ok=True)
                self._stream = open(self._folder / ("forum_%s.log" % day),
                                    "a", encoding="utf-8")
                self._day = day
            except OSError:
                self._stream = None
        return self._stream

    def _close(self) -> None:
        if self._stream is not None:
            try:
                self._stream.close()
            except Exception:
                pass
        self._stream = None

    def emit(self, record: logging.LogRecord) -> None:
        with self._io_lock:
            stream = self._stream_for_today()
            if stream is None:
                return
            try:
                stream.write(self.format(record) + "\n")
                stream.flush()
            except Exception:
                pass

    def close(self) -> None:
        with self._io_lock:
            self._close()
        super().close()


class _SignalHandler(logging.Handler):
    def __init__(self, emitter) -> None:
        super().__init__()
        self._emitter = emitter

    def emit(self, record: logging.LogRecord) -> None:
        try:
            self._emitter(record.levelname, self.format(record))
        except Exception:
            pass


def current_log_file() -> Path:
    return paths.logs_dir() / ("forum_%s.log" % datetime.now().strftime("%Y%m%d"))


def _prune(folder: Path, keep_days: int = KEEP_DAYS) -> None:
    try:
        cutoff = time.time() - keep_days * 86400
        for p in folder.glob("forum_*.log"):
            try:
                if p.stat().st_mtime < cutoff:
                    p.unlink()
            except OSError:
                pass
    except Exception:
        pass


def setup(level: int = logging.INFO) -> logging.Logger:
    """初始化根日志器（幂等）。"""
    global _initialized
    root = logging.getLogger(ROOT_NAME)
    with _lock:
        if _initialized:
            return root
        root.setLevel(logging.DEBUG)
        root.propagate = False
        fmt = logging.Formatter(LOG_FORMAT, DATE_FORMAT)

        try:
            fh = _DailyFileHandler(paths.logs_dir())
            fh.setFormatter(fmt)
            fh.setLevel(logging.DEBUG)
            root.addHandler(fh)
            _prune(paths.logs_dir())
        except Exception:
            pass

        sig = _SignalHandler(lambda lv, tx: bus().message.emit(lv, tx))
        sig.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s", DATE_FORMAT))
        sig.setLevel(logging.DEBUG)
        root.addHandler(sig)

        # 开发态（未打包）时同时输出到控制台
        if not getattr(sys, "frozen", False):
            try:
                ch = logging.StreamHandler(sys.stderr)
                ch.setFormatter(fmt)
                ch.setLevel(level)
                root.addHandler(ch)
            except Exception:
                pass

        _initialized = True
    return root


def get_logger(name: str = "app") -> logging.Logger:
    setup()
    return logging.getLogger("%s.%s" % (ROOT_NAME, name))


def hook_excepthook() -> None:
    """把未捕获异常也写进日志，避免界面直接崩掉看不到原因。"""
    log = get_logger("crash")
    previous = sys.excepthook

    def _hook(etype, value, tb):
        try:
            log.critical("未捕获异常", exc_info=(etype, value, tb))
        except Exception:
            pass
        try:
            previous(etype, value, tb)
        except Exception:
            pass

    sys.excepthook = _hook

    def _thread_hook(args):
        try:
            log.critical("线程未捕获异常（%s）" % getattr(args, "thread", "?"),
                         exc_info=(args.exc_type, args.exc_value, args.exc_traceback))
        except Exception:
            pass

    try:
        threading.excepthook = _thread_hook
    except Exception:
        pass
