# -*- coding: utf-8 -*-
"""更新检查与下载：探测远端更新包 → 比对本地记录 → 流式下载 → 静默安装。

* 主更新源是发布清单里的 GitHub Release 直链（安装包 ``forum_setup.exe``）；
  下载时按「直连 → DoH 修复 DNS → 公共加速 → 服务器反代」逐级回退
  （见 :mod:`app.netfallback`）；拿不到清单时回退到
  :data:`constants.UPDATE_EXE_URL` 的指纹探测
* 本地记录：``~/.Cr/forum/update/manifest.json``（``etag`` / ``last_modified`` / ``size`` / ``checked_at``）
* 每个版本的安装包单独放在 ``~/.Cr/forum/update/<版本>/`` 下，互不污染
* 下载物按文件名区分：``forum_setup*.exe`` 走静默安装（``/SILENT``，装完由安装器
  自己拉起客户端），其余（旧版裸 exe）走热替换脚本
* 安装包**不再经 ``.cmd`` 中转**：由 :func:`schedule_install_on_exit` 登记到 :mod:`atexit`，
  进程退出时用 ``CREATE_NO_WINDOW`` 直接唤起（消除黑框与卡住的控制台窗口）
* 约定：**对外函数都不抛异常**（唯一例外：:func:`launch_installer` 的「立即安装」
  会 ``sys.exit(0)`` 结束当前进程），失败原因写进 :class:`UpdateInfo.message`（中文，可直接展示）
"""

from __future__ import annotations

import atexit
import hashlib
import json
import os
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

import requests
from PyQt6.QtCore import QObject, pyqtSignal

from . import api, constants, logger, netfallback, paths, releases, util

_log = logger.get_logger("updater")

DEFAULT_TIMEOUT = (5, 12)
# 下载超时（连接, 读取）；连接失败/超时即升级到下一级下载源
DOWNLOAD_TIMEOUT = (20, 30)
CHUNK_SIZE = 64 * 1024
INSTALLER_NAME = "forum_setup.exe"          # 发布清单 / GitHub Release 上的安装包名
SCRIPT_NAME = "apply_update.cmd"
PENDING_NAME = "pending.json"               # 「退出时自动安装」的登记文件
WAIT_SECONDS = 60
# Inno Setup 静默安装参数（进度条可见、不走向导、装完不自动拉起）
INSTALLER_ARGS = ("/SILENT", "/NORESTART", "/CLOSEAPPLICATIONS", "/SUPPRESSMSGBOXES")

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
    filename: str = ""
    sha256: str = ""


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
    request_headers = {"User-Agent": constants.CLIENT_UA,
                       **constants.CLIENT_HEADERS}
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
                      notes=(notes,) if notes else (),
                      filename=str(getattr(release, "filename", "") or ""),
                      sha256=str(getattr(release, "sha256", "") or ""))


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
    """把工作线程里的进度/阶段回调排队到主线程执行（控件不可跨线程访问）。"""

    progressed = pyqtSignal(int, int)
    staged = pyqtSignal(str)

    def __init__(self, callback=None, on_stage=None) -> None:
        super().__init__()
        self._callback = callback
        self._stage_callback = on_stage
        if callable(callback):
            self.progressed.connect(self._on_progress)
        if callable(on_stage):
            self.staged.connect(self._on_stage)

    def _on_progress(self, done: int, total: int) -> None:
        _emit(self._callback, done, total)

    def _on_stage(self, label: str) -> None:
        _emit(self._stage_callback, label)

    def emit_progress(self, done: int, total: int) -> None:
        try:
            self.progressed.emit(int(done), int(total))
        except Exception as exc:  # noqa: BLE001
            _log.debug("进度回调失败：%s", exc)

    def emit_stage(self, label: str) -> None:
        try:
            self.staged.emit(str(label or ""))
        except Exception as exc:  # noqa: BLE001
            _log.debug("阶段回调失败：%s", exc)


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

    headers = {"User-Agent": constants.CLIENT_UA, **constants.CLIENT_HEADERS}
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


def _remove_part(dest) -> None:
    """删除断点文件（换下载源时必须重下，避免混合不同来源的字节）。"""
    part = Path(str(dest) + ".part")
    try:
        if part.is_file():
            part.unlink()
    except OSError as exc:  # noqa: PERF203
        _log.debug("清理断点文件失败：%s", exc)


def download_with_fallback(attempts, dest, *, expected: int = 0,
                           on_progress=None, on_stage=None,
                           timeout=DOWNLOAD_TIMEOUT) -> tuple[bool, str]:
    """按顺序尝试多级下载源；全部失败返回 ``(False, 最后一次错误)``。

    ``attempts`` 形如 ``[(标签, 地址, 是否用 DoH), ...]``（见
    :func:`app.netfallback.download_attempts`）。只有第一次尝试允许断点续传；
    换源时先删掉 ``.part``，保证不会把不同来源的字节拼在一起。
    """
    items = list(attempts or [])
    if not items:
        return False, "没有可用的下载源"
    last_error = ""
    for index, item in enumerate(items):
        try:
            label, url, use_doh = item
        except Exception:  # noqa: BLE001
            continue
        if not str(url or "").strip():
            continue
        _emit(on_stage, str(label or "下载"))
        if index > 0:
            _remove_part(dest)
        try:
            if use_doh:
                with netfallback.doh_dns():
                    ok, error = download_to(url, dest, expected=expected,
                                            resume=(index == 0),
                                            on_progress=on_progress,
                                            timeout=timeout)
            else:
                ok, error = download_to(url, dest, expected=expected,
                                        resume=(index == 0),
                                        on_progress=on_progress,
                                        timeout=timeout)
        except Exception as exc:  # noqa: BLE001
            ok, error = False, str(exc) or "下载失败"
        if ok:
            return True, ""
        last_error = error or "下载失败"
        _log.info("下载源「%s」失败：%s", label, last_error)
    return False, last_error or "下载失败"


def _write_script(path: Path, text: str) -> None:
    """写 ``.cmd``：文本已经是 CRLF，必须用 ``newline=""`` 原样写出。

    若用 ``newline="\\r\\n"``，已有的 ``\\n`` 会被再翻译一次得到 ``\\r\\r\\n``。
    实测该换行 cmd 尚能容忍，真正的致命点是 ``for /L`` 的循环变量必须
    落成双百分号 ``%%i``（见 :func:`_script_text` 注释）；这里保持原样
    写出，避免任何隐式二次翻译。
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="")


def _basename_from_url(url: str) -> str:
    """取 URL 路径末段（GitHub 直链 → ``forum_setup.exe``）。"""
    try:
        return str(Path(urlparse(str(url or "")).path).name)
    except Exception:  # noqa: BLE001
        return ""


def asset_name(url: str, filename: str = "") -> str:
    """下载后的本地文件名：清单 filename > URL 末段 > 安装包默认名。

    只接受 ``.exe``（避开远端下发奇怪后缀），名字统一走
    :func:`paths.safe_component` 清洗，杜绝路径穿越。
    """
    for candidate in (filename, _basename_from_url(url)):
        name = paths.safe_component(candidate, "")
        if name and name.lower().endswith(".exe"):
            return name
    return INSTALLER_NAME


def download_dir(info) -> Path:
    """该版本的下载目录：``~/.Cr/forum/update/<版本>/``（版本缺失则退回上级）。"""
    return paths.update_dir(str(getattr(info, "version", "") or "").strip())


def _sha256_file(path) -> str:
    hasher = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def _discard(path) -> None:
    """删掉校验失败的下载物（含断点文件），避免下次续传复用坏包。"""
    for candidate in (Path(str(path)), Path(str(path) + ".part")):
        try:
            if candidate.is_file():
                candidate.unlink()
        except OSError as exc:  # noqa: PERF203
            _log.debug("清理损坏的更新包失败：%s", exc)


def download_update(info, on_progress=None, on_done=None, on_stage=None) -> None:
    """异步下载更新包到 ``~/.Cr/forum/update/<版本>/<文件名>``。

    * 文件名优先用发布清单的 ``filename``，其次按 URL 末段推断
    * 下载按「直连 → DoH 修复 DNS → 公共加速 → 服务器反代」逐级回退
    * 清单提供 ``sha256`` 时会校验，不匹配即删除并报错
    * ``on_progress(done, total)``：主线程回调，``total`` 未知时为 0
    * ``on_stage(label)``：切换到下一级下载源时的主线程回调
    * ``on_done(exe_path, error)``：主线程回调，``error`` 为空串表示成功
    """
    url = str(getattr(info, "url", "") or constants.UPDATE_EXE_URL or "").strip()
    expected = int(getattr(info, "size", 0) or 0)
    digest = str(getattr(info, "sha256", "") or "").strip().lower()
    name = asset_name(url, str(getattr(info, "filename", "") or ""))
    attempts = netfallback.download_attempts(url, name) or [("直连", url, False)]
    relay = _ProgressRelay(on_progress, on_stage)

    def _work() -> str:
        final = download_dir(info) / name
        ok, error = download_with_fallback(attempts, final, expected=expected,
                                           on_progress=relay.emit_progress,
                                           on_stage=relay.emit_stage)
        if not ok:
            raise RuntimeError(error or "下载失败")
        if digest:
            actual = _sha256_file(final)
            if actual.lower() != digest:
                _log.warning("更新包校验失败：%s ≠ %s", actual, digest)
                _discard(final)
                raise RuntimeError("更新包校验失败（校验和不匹配），请重新下载")
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
    """旧版替换脚本：等主程序退出 → 覆盖可执行文件 → 重新启动。"""
    name = target.name
    lines = [
        "@echo off",
        "setlocal enableextensions",
        'set "SRC=' + str(source) + '"',
        'set "DST=' + str(target) + '"',
        "rem wait for the app to exit (max {} seconds), then replace it".format(WAIT_SECONDS),
        # 批处理文件里循环变量必须写 %%i；用 % 格式化会把 %% 折叠成单个 %，
        # cmd 解析到 `for /L %i` 时报「此时不应有 i」并整段中断，
        # 表现为「程序退了但安装器不启动」。
        "for /L %%i in (1,1,{}) do (".format(WAIT_SECONDS),
        '  tasklist /fi "imagename eq ' + name + '" 2>nul | findstr /i "' + name + '" >nul',
        "  if errorlevel 1 goto copy",
        "  ping -n 2 127.0.0.1 >nul",
        ")",
        ":copy",
        'move /y "%SRC%" "%DST%" >nul',
        'start "" "%DST%"',
        'start "" "%DST%"',
        'del "%~f0" >nul 2>&1',
        "endlocal",
        "",
    ]
    return "\r\n".join(lines)


def _spawn_installer(setup: Path) -> None:
    """用 ``CREATE_NO_WINDOW`` 直接唤起安装包（不再经 ``.cmd`` 中转）。

    * ``shell=False`` + 可执行文件全路径，完全不经过命令解释器；
    * ``CREATE_NO_WINDOW`` 不给子进程分配控制台窗口 —— 这正是旧版 ``.cmd``
      中转「闪黑框 / 控制台一直开着卡住不响应」的根因；
    * 标准流接空设备，避免把 GUI 进程无效的控制台句柄继承给子进程；
    * ``/CLOSEAPPLICATIONS`` 让安装器用 Restart Manager 关掉仍在运行的客户端，
      补偿被移除的「批处理等主程序退出」逻辑。
    """
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    kwargs = {"creationflags": flags, "shell": False, "close_fds": True}
    devnull = getattr(subprocess, "DEVNULL", None)
    if devnull is not None:
        kwargs.update(stdin=devnull, stdout=devnull, stderr=devnull)
    subprocess.Popen([str(setup), *INSTALLER_ARGS], **kwargs)


def _spawn_script(script: Path) -> None:
    """脱离当前进程启动 .cmd（父进程退出不影响它继续跑）。

    子进程标准流接到空设备：GUI 程序没有有效控制台句柄，
    直接继承会让 cmd 的初始化不稳定。
    """
    flags = (getattr(subprocess, "DETACHED_PROCESS", 0)
             | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0))
    kwargs = {"creationflags": flags, "close_fds": True}
    devnull = getattr(subprocess, "DEVNULL", None)
    if devnull is not None:
        kwargs.update(stdin=devnull, stdout=devnull, stderr=devnull)
    subprocess.Popen(["cmd", "/c", str(script)], **kwargs)


def is_installer(path) -> bool:
    """下载物是否是安装包（Inno Setup 产物 ``forum_setup*.exe``）。"""
    return Path(str(path or "")).name.lower().startswith("forum_setup")


def _quit_app() -> None:
    try:
        from PyQt6.QtWidgets import QApplication
        instance = QApplication.instance()
        if instance is not None:
            instance.quit()
    except Exception as exc:  # noqa: BLE001
        _log.debug("退出当前进程失败：%s", exc)


# ──────────────────── 退出时安装（atexit 钩子） ────────────────────
#
# 安装包不再写 ``.cmd`` 中转：而是在退出阶段用 ``CREATE_NO_WINDOW`` 直接唤起。
# 钩子只在首次登记时注册，进程真正退出后才拉起安装器，
# 因此不会在客户端仍占用 ``forum.exe`` 时启动安装程序。

_EXIT_INSTALLER: Path | None = None
_EXIT_HOOK_REGISTERED = False


def _run_exit_installer() -> None:
    """``atexit`` 回调：进程退出阶段唤起已登记的安装包。"""
    global _EXIT_INSTALLER
    path = _EXIT_INSTALLER
    _EXIT_INSTALLER = None
    if path is None:
        return
    try:
        if not Path(path).is_file():
            _log.warning("退出时安装：安装包已不存在，跳过：%s", path)
            return
        _spawn_installer(Path(path))
        _log.info("退出时已唤起安装包：%s", path)
    except Exception as exc:  # noqa: BLE001
        _log.error("退出时唤起安装包失败：%s", exc, exc_info=True)


def schedule_install_on_exit(exe_path) -> bool:
    """登记「退出程序后自动安装」；安装包不存在时返回 False。

    只在首次登记时注册 ``atexit`` 钩子（避免重复），进程退出后由
    :func:`_run_exit_installer` 用 ``CREATE_NO_WINDOW`` 直接唤起安装包。
    """
    global _EXIT_INSTALLER, _EXIT_HOOK_REGISTERED
    target = Path(str(exe_path or "")).expanduser()
    if not target.is_file():
        return False
    _EXIT_INSTALLER = target
    if not _EXIT_HOOK_REGISTERED:
        atexit.register(_run_exit_installer)
        _EXIT_HOOK_REGISTERED = True
    _log.info("已登记退出时自动安装：%s", target)
    return True


def launch_installer(exe_path) -> tuple[bool, str]:
    """启动更新并退出当前进程，返回 ``(是否成功, 中文提示)``。

    * 安装包（``forum_setup*.exe``）→ 登记退出钩子后立即结束当前进程；
      进程退出时用 ``CREATE_NO_WINDOW`` 直接唤起安装包（``/SILENT``，
      不走向导），装完由安装器自己拉起客户端
    * 其它（旧版裸 exe）→ 保留原有热替换脚本

    开发态（``sys.executable`` 是 python.exe）直接拒绝，不做任何替换。
    """
    try:
        if not getattr(sys, "frozen", False):
            return (False, "当前为开发态运行，请用打包后的程序测试更新")

        source = Path(str(exe_path or "")).expanduser()
        if not source.is_file():
            return (False, "更新包不存在，请重新下载")

        if is_installer(source):
            if not schedule_install_on_exit(source):
                return (False, "更新包不存在，请重新下载")
            # 双保险：先让事件循环退出；即使下面这句 SystemExit 被 Qt 吞掉，
            # main() 正常收尾时也会触发 atexit，安装包照样会被唤起。
            _quit_app()
            _log.info("立即安装：已登记退出后唤起 %s", source)
            sys.exit(0)

        target = Path(sys.executable)
        if source.resolve() == target.resolve():
            return (False, "更新包与当前程序路径相同，无需替换")

        script = paths.update_dir() / SCRIPT_NAME
        _write_script(script, _script_text(source, target))
        _spawn_script(script)
        _log.info("已启动更新脚本：%s → %s", source, target)
        _quit_app()
        return (True, "更新脚本已启动，程序将退出并自动完成替换")
    except SystemExit:
        raise
    except Exception as exc:  # noqa: BLE001
        _log.error("启动更新失败：%s", exc, exc_info=True)
        return (False, "启动更新失败：%s" % exc)


# ────────────────────── 退出时自动安装 ──────────────────────


def pending_install_path() -> Path:
    """「退出时自动安装」的登记文件（放在 update 根目录，跨版本共用一份）。"""
    return paths.update_dir() / PENDING_NAME


def set_pending_install(path, version: str = "") -> bool:
    """登记「退出时自动安装」；安装包不存在或写失败时返回 False。"""
    try:
        target = Path(str(path or "")).expanduser()
        if not target.is_file():
            return False
        payload = {"path": str(target), "version": str(version or ""),
                   "created_at": time.time()}
        dest = pending_install_path()
        dest.parent.mkdir(parents=True, exist_ok=True)
        tmp = dest.with_suffix(dest.suffix + ".tmp")
        tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2),
                       encoding="utf-8")
        os.replace(tmp, dest)
        _log.info("已登记退出时自动安装：%s", target)
        return True
    except Exception as exc:  # noqa: BLE001
        _log.warning("登记退出时自动安装失败：%s", exc)
        return False


def pending_install() -> dict | None:
    """读取未完成的「退出时自动安装」；没有（或安装包已被删）时返回 None。"""
    try:
        path = pending_install_path()
        data = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}
    except Exception as exc:  # noqa: BLE001
        _log.debug("读取待安装记录失败：%s", exc)
        data = {}
    if not isinstance(data, dict):
        return None
    target = str(data.get("path") or "").strip()
    if not target:
        return None
    if not Path(target).expanduser().is_file():
        clear_pending_install()
        return None
    return {"path": target, "version": str(data.get("version") or "")}


def clear_pending_install() -> None:
    """清掉「退出时自动安装」登记。"""
    try:
        path = pending_install_path()
        if path.is_file():
            path.unlink()
    except Exception as exc:  # noqa: BLE001
        _log.debug("清理待安装记录失败：%s", exc)


def run_pending_install() -> bool:
    """退出程序时执行「退出时自动安装」；返回是否已登记到退出钩子。"""
    info = pending_install()
    if not info:
        return False
    if not schedule_install_on_exit(info["path"]):
        return False
    clear_pending_install()
    _log.info("已登记退出时安装：%s", info["path"])
    return True
