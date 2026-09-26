# -*- coding: utf-8 -*-
"""更新检查与下载：探测远端更新包 → 比对本地记录 → 流式下载 → 启动替换脚本。

* 更新源固定为 :data:`constants.UPDATE_EXE_URL`（常量内已做混淆，本模块不出现明文地址）
* 本地记录：``~/.Cr/forum/update/manifest.json``（``etag`` / ``last_modified`` / ``size`` / ``checked_at``）
* 约定：**对外函数都不抛异常**，失败原因写进 :class:`UpdateInfo.message`（中文，可直接展示）
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

import requests
from PyQt6.QtCore import QObject, pyqtSignal

from . import api, constants, logger, paths, releases, util

_log = logger.get_logger("updater")

DEFAULT_TIMEOUT = (5, 12)
DOWNLOAD_TIMEOUT = (5, 60)
CHUNK_SIZE = 64 * 1024
PART_NAME = "forum_new.exe.part"
EXE_NAME = "forum_new.exe"
SCRIPT_NAME = "apply_update.cmd"
WAIT_SECONDS = 60

UNAVAILABLE_TEXT = "更新服务暂不可用"
FAILED_TEXT = "检查更新失败"
LATEST_TEXT = "当前已是最新版本"


@dataclass
class UpdateInfo:
    """一次更新检查的结果；``message`` 始终是可直接展示的中文文案。"""

    available: bool
    version: str = ""
    url: str = ""
    size: int = 0
    message: str = ""
    mandatory: bool = False
    notes: tuple = ()


# ────────────────────────── 版本 / 本地记录 ──────────────────────────


def current_version() -> str:
    """当前客户端版本号。"""
    try:
        return str(constants.APP_VERSION)
    except Exception:  # noqa: BLE001
        return ""


def local_manifest_path() -> Path:
    """本地更新记录文件。"""
    return paths.update_dir() / "manifest.json"


def _read_manifest() -> dict:
    try:
        path = local_manifest_path()
        if path.is_file():
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return data
    except Exception as exc:  # noqa: BLE001
        _log.debug("读取更新记录失败：%s", exc)
    return {}


def _write_manifest(**fields) -> None:
    """合并写入更新记录（临时文件 + 原子替换）。"""
    try:
        data = _read_manifest()
        for key, value in fields.items():
            if value is not None:
                data[key] = value
        data["checked_at"] = float(fields.get("checked_at") or time.time())
        path = local_manifest_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(tmp, path)
    except Exception as exc:  # noqa: BLE001
        _log.debug("写入更新记录失败：%s", exc)


# ────────────────────────── 远端探测 ──────────────────────────


class _Unavailable(Exception):
    """更新源不可达（404 / 403 / 超时 / 断网）。"""


def _normalize(headers) -> dict:
    """响应头 → 全小写 key 的普通字典。"""
    out: dict = {}
    try:
        for key, value in dict(headers or {}).items():
            out[str(key).lower()] = str(value)
    except Exception:  # noqa: BLE001
        pass
    return out


def _size_from_headers(headers: dict) -> int:
    """取文件总大小：优先 ``Content-Range``（Range 请求），否则 ``Content-Length``。"""
    content_range = str(headers.get("content-range") or "")
    if "/" in content_range:
        total = content_range.rsplit("/", 1)[-1].strip()
        if total.isdigit():
            return int(total)
    length = str(headers.get("content-length") or "").strip()
    return int(length) if length.isdigit() else 0


def _probe(url: str, timeout) -> tuple[dict, int]:
    """轻量探测更新包 → ``(响应头, 文件大小)``。

    先发 ``HEAD``；方法不被支持或失败时降级为 ``GET`` + ``Range: bytes=0-0``。
    不可达时抛 :class:`_Unavailable`。
    """
    request_headers = {"User-Agent": constants.CLIENT_UA}
    head_error = ""
    try:
        resp = requests.head(url, timeout=timeout, allow_redirects=True,
                             headers=request_headers)
        try:
            if resp.status_code < 400:
                headers = _normalize(resp.headers)
                return headers, _size_from_headers(headers)
            head_error = "HTTP %s" % resp.status_code
        finally:
            resp.close()
    except Exception as exc:  # noqa: BLE001
        head_error = str(exc) or "网络不可达"

    try:
        range_headers = dict(request_headers)
        range_headers["Range"] = "bytes=0-0"
        with requests.get(url, timeout=timeout, allow_redirects=True,
                          headers=range_headers, stream=True) as resp:
            if resp.status_code >= 400:
                raise _Unavailable("HTTP %s" % resp.status_code)
            headers = _normalize(resp.headers)
            return headers, _size_from_headers(headers)
    except Exception as exc:  # noqa: BLE001
        _log.info("更新源探测失败：%s（HEAD：%s）", exc, head_error)
        raise _Unavailable(str(exc) or head_error or "网络不可达") from None


# ────────────────────────── 检查更新 ──────────────────────────

_pending_signature: dict | None = None


def _check_release_catalog():
    """优先用发布清单判定；拿不到清单时返回 None（交给指纹探测兜底）。"""
    global _pending_signature
    try:
        found = releases.check(current_version())
    except Exception as exc:  # noqa: BLE001
        _log.info("发布清单检查失败：%s", exc)
        return None
    if not found.known:
        return None
    release = found.release
    if not found.available:
        _pending_signature = None
        return UpdateInfo(False, version=found.version or "",
                          url=str(getattr(release, "url", "") or ""),
                          size=int(getattr(release, "size", 0) or 0),
                          message=found.message or LATEST_TEXT)
    url = str(getattr(release, "url", "") or "") or str(constants.UPDATE_EXE_URL)
    size = int(getattr(release, "size", 0) or 0)
    notes = str(getattr(release, "notes", "") or "").strip()
    _pending_signature = None
    _log.info("发布清单发现新版本：%s", found.version)
    return UpdateInfo(True, version=found.version or "", url=url, size=size,
                      message=found.message or ("发现新版本（%s）" % found.version),
                      mandatory=bool(getattr(release, "mandatory", False)),
                      notes=(notes,) if notes else ())


def check_for_update(*, manifest_url=None, timeout=DEFAULT_TIMEOUT) -> UpdateInfo:
    """检查更新（阻塞，不抛异常）。

    优先用发布清单（``/api/app/releases``）判定；拿不到清单时再用远端文件指纹探测。
    端点 404/403/不可达 → ``available=False`` 且 ``message="更新服务暂不可用"``；
    远端签名与本地记录一致 → ``available=False`` 且 ``message="当前已是最新版本"``。
    """
    global _pending_signature
    url = str(manifest_url or constants.UPDATE_EXE_URL or "").strip()
    if not url:
        return UpdateInfo(False, message=UNAVAILABLE_TEXT)

    from_catalog = _check_release_catalog()
    if from_catalog is not None:
        return from_catalog

    try:
        headers, size = _probe(url, timeout)
    except Exception as exc:  # noqa: BLE001
        _log.info("检查更新失败：%s", exc)
        return UpdateInfo(False, message=UNAVAILABLE_TEXT)

    try:
        signature = {
            "etag": headers.get("etag") or "",
            "last_modified": headers.get("last-modified") or "",
            "size": int(size or 0),
        }
        version = signature["last_modified"] or time.strftime("%Y.%m.%d.%H%M",
                                                             time.localtime())
        manifest = _read_manifest()

        if not manifest:
            # 首次检查：没有可比对的历史记录，只记基线，避免刚装上就误报有新版
            _write_manifest(**signature)
            _log.info("已记录更新源基线：%s", signature)
            return UpdateInfo(False, version=version, url=url,
                              size=signature["size"], message=LATEST_TEXT)

        if not any(manifest.get(key) != value for key, value in signature.items()):
            _write_manifest(checked_at=time.time())
            return UpdateInfo(False, version=version, url=url,
                              size=signature["size"], message=LATEST_TEXT)

        message = "发现新版本（%s）" % (version or "未知时间")
        if signature["size"]:
            message += "，大小 %s" % util.human_size(signature["size"])
        _pending_signature = dict(signature)
        _log.info("发现新版本：%s", signature)
        return UpdateInfo(True, version=version, url=url,
                          size=signature["size"], message=message)
    except Exception as exc:  # noqa: BLE001
        _log.error("检查更新异常：%s", exc, exc_info=True)
        return UpdateInfo(False, message=FAILED_TEXT)


def _emit(callback, *args) -> None:
    """调用回调（不抛异常）。"""
    if not callable(callback):
        return
    try:
        callback(*args)
    except Exception as exc:  # noqa: BLE001
        _log.warning("更新回调执行失败：%s", exc)


def check_async(on_done, *, manifest_url=None, label="检查更新") -> None:
    """异步检查更新；``on_done(UpdateInfo)`` 在主线程回调，绝不抛异常。"""
    def _work():
        return check_for_update(manifest_url=manifest_url)

    def _ok(info):
        _emit(on_done, info if isinstance(info, UpdateInfo)
              else UpdateInfo(False, message=FAILED_TEXT))

    def _fail(message):
        _emit(on_done, UpdateInfo(False, message="%s：%s" % (FAILED_TEXT, message)))

    try:
        api.run_async(_work, _ok, _fail, label=label)
    except Exception as exc:  # noqa: BLE001
        _log.error("异步检查更新启动失败：%s", exc, exc_info=True)
        _emit(on_done, UpdateInfo(False, message="%s：%s" % (FAILED_TEXT, exc)))


# ────────────────────────── 下载 ──────────────────────────


class _ProgressRelay(QObject):
    """把工作线程里的进度回调排队到主线程执行（控件不可跨线程访问）。"""

    progressed = pyqtSignal(int, int)

    def __init__(self, callback=None) -> None:
        super().__init__()
        self._callback = callback
        if callable(callback):
            self.progressed.connect(self._on_progress)

    def _on_progress(self, done: int, total: int) -> None:
        _emit(self._callback, done, total)

    def emit_progress(self, done: int, total: int) -> None:
        try:
            self.progressed.emit(int(done), int(total))
        except Exception as exc:  # noqa: BLE001
            _log.debug("进度回调失败：%s", exc)


def download_to(url: str, dest, *, expected: int = 0, resume: bool = True,
                on_progress=None, timeout=DOWNLOAD_TIMEOUT,
                chunk_size: int = CHUNK_SIZE) -> tuple[bool, str]:
    """流式下载到 ``dest``（支持 Range 断点续传），返回 ``(ok, 中文错误)``。

    * 先写 ``dest.part``；若已存在且 ``resume=True``，带 ``Range`` 续传
    * 服务器不支持断点时（回 200 而非 206）自动从头重下
    * 完成后原子替换为 ``dest``
    """
    target = Path(dest)
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        return False, "无法创建下载目录：%s" % exc
    part = target.with_suffix(target.suffix + ".part")

    offset = 0
    if resume and part.is_file():
        try:
            offset = int(part.stat().st_size)
        except OSError:
            offset = 0
    if expected > 0 and offset >= expected:
        try:
            os.replace(part, target)
            if on_progress is not None:
                try:
                    on_progress(expected, expected)
                except Exception:  # noqa: BLE001
                    pass
            return True, ""
        except OSError:
            offset = 0

    headers = {"User-Agent": constants.CLIENT_UA}
    mode = "wb"
    if offset > 0:
        headers["Range"] = "bytes=%d-" % offset
        mode = "ab"

    done = offset
    try:
        with requests.get(url, timeout=timeout, headers=headers,
                          stream=True, allow_redirects=True) as resp:
            if resp.status_code >= 400:
                return False, "下载失败（HTTP %s）" % resp.status_code
            if offset > 0 and resp.status_code != 206:
                # 服务器不支持断点续传 → 从头来
                offset = 0
                mode = "wb"
            length = str(resp.headers.get("Content-Length") or "").strip()
            remaining = int(length) if length.isdigit() else 0
            if expected > 0:
                total = expected
            elif remaining > 0:
                total = offset + remaining
            else:
                total = 0
            done = offset
            if on_progress is not None:
                try:
                    on_progress(done, total)
                except Exception:  # noqa: BLE001
                    pass
            with open(part, mode) as handle:
                for chunk in resp.iter_content(chunk_size):
                    if not chunk:
                        continue
                    handle.write(chunk)
                    done += len(chunk)
                    if on_progress is not None:
                        try:
                            on_progress(done, total)
                        except Exception:  # noqa: BLE001
                            pass
    except Exception as exc:  # noqa: BLE001
        return False, "下载失败：%s" % exc

    if done <= 0:
        return False, "更新包内容为空"
    if expected > 0 and done < expected:
        return False, "下载不完整（%s / %s）" % (util.human_size(done),
                                                util.human_size(expected))
    try:
        os.replace(part, target)
    except OSError as exc:
        return False, "写入更新包失败：%s" % exc
    return True, ""


def download_update(info, on_progress=None, on_done=None) -> None:
    """异步下载更新包到 ``~/.Cr/forum/update/forum_new.exe``。

    * ``on_progress(done, total)``：主线程回调，``total`` 未知时为 0
    * ``on_done(exe_path, error)``：主线程回调，``error`` 为空串表示成功
    """
    url = str(getattr(info, "url", "") or constants.UPDATE_EXE_URL or "").strip()
    expected = int(getattr(info, "size", 0) or 0)
    relay = _ProgressRelay(on_progress)

    def _work() -> str:
        final = paths.update_dir() / EXE_NAME
        ok, error = download_to(url, final, expected=expected, resume=True,
                                on_progress=relay.emit_progress)
        if not ok:
            raise RuntimeError(error or "下载失败")
        return str(final)

    def _ok(path) -> None:
        if _pending_signature:
            _write_manifest(**_pending_download_signature())
        _log.info("更新包已下载：%s", path)
        _emit(on_done, str(path), "")

    def _fail(message) -> None:
        _log.warning("更新包下载失败：%s", message)
        _emit(on_done, None, str(message))

    try:
        api.run_async(_work, _ok, _fail, label="下载更新")
    except Exception as exc:  # noqa: BLE001
        _log.error("启动下载失败：%s", exc, exc_info=True)
        _emit(on_done, None, str(exc))


def _pending_download_signature() -> dict:
    """下载完成后写回本地的基线签名（拿不到时按当前远端重新探测一次）。"""
    global _pending_signature
    if _pending_signature:
        signature = dict(_pending_signature)
        _pending_signature = None
        return signature
    try:
        headers, size = _probe(str(constants.UPDATE_EXE_URL), DEFAULT_TIMEOUT)
        return {"etag": headers.get("etag") or "",
                "last_modified": headers.get("last-modified") or "",
                "size": int(size or 0)}
    except Exception:  # noqa: BLE001
        return {}


# ────────────────────────── 安装替换 ──────────────────────────


def _script_text(source: Path, target: Path) -> str:
    """替换脚本：等主程序退出 → 覆盖可执行文件 → 重新启动。"""
    name = target.name
    lines = [
        "@echo off",
        "setlocal enableextensions",
        'set "SRC=' + str(source) + '"',
        'set "DST=' + str(target) + '"',
        "rem wait for the app to exit (max %d seconds), then replace it" % WAIT_SECONDS,
        "for /L %%i in (1,1,%d) do (" % WAIT_SECONDS,
        '  tasklist /fi "imagename eq ' + name + '" 2>nul | findstr /i "' + name + '" >nul',
        "  if errorlevel 1 goto copy",
        "  timeout /t 1 /nobreak >nul",
        ")",
        ":copy",
        'move /y "%SRC%" "%DST%" >nul',
        'start "" "%DST%"',
        'del "%~f0" >nul 2>&1',
        "endlocal",
        "",
    ]
    return "\r\n".join(lines)


def _quit_app() -> None:
    try:
        from PyQt6.QtWidgets import QApplication
        instance = QApplication.instance()
        if instance is not None:
            instance.quit()
    except Exception as exc:  # noqa: BLE001
        _log.debug("退出当前进程失败：%s", exc)


def launch_installer(exe_path) -> tuple[bool, str]:
    """启动替换脚本并退出当前进程，返回 ``(是否成功, 中文提示)``。

    开发态（``sys.executable`` 是 python.exe）直接拒绝，不做任何替换。
    """
    try:
        if not getattr(sys, "frozen", False):
            return (False, "当前为开发态运行，请用打包后的程序测试更新")

        source = Path(str(exe_path or "")).expanduser()
        if not source.is_file():
            return (False, "更新包不存在，请重新下载")

        target = Path(sys.executable)
        if source.resolve() == target.resolve():
            return (False, "更新包与当前程序路径相同，无需替换")

        script = paths.update_dir() / SCRIPT_NAME
        script.parent.mkdir(parents=True, exist_ok=True)
        script.write_text(_script_text(source, target), encoding="utf-8", newline="\r\n")

        flags = (getattr(subprocess, "DETACHED_PROCESS", 0)
                 | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0))
        subprocess.Popen(["cmd", "/c", str(script)], creationflags=flags, close_fds=True)
        _log.info("已启动更新脚本：%s → %s", source, target)
        _quit_app()
        return (True, "更新脚本已启动，程序将退出并自动完成替换")
    except Exception as exc:  # noqa: BLE001
        _log.error("启动更新脚本失败：%s", exc, exc_info=True)
        return (False, "启动更新失败：%s" % exc)
