# -*- coding: utf-8 -*-
"""Live2D 桌宠资源提供者：下载 HEI.lpk → 解密解包 → 归一化 → 缓存。

缓存全部落在 ``~/.Cr/forum/Live2D/``（可用 ``CRFORUM_DATA_DIR`` 或构造参数覆盖）::

    Live2D/
    ├── HEI.lpk                     下载缓存（只下一次，之后复用）
    ├── tmp/unpack/<角色>/           解包中间产物（用完即删）
    ├── HEI4.0/                     归一化后的模型目录
    │   ├── HEI4.0.model3.json
    │   ├── motions/*.motion3.json
    │   ├── sounds/*.wav
    │   └── FileReferences_*        纹理 / .moc3 / 表情 / 物理 / Pose ...
    └── model.json                  指针文件（当前模型与解包时间）

本模块只负责「取到能被 live2d-py 加载的 .model3.json」，不做渲染。

命令行验收：在仓库根目录（``forum-windows``）下执行::

    python -m app.live2d.provider
"""

from __future__ import annotations

import json
import shutil
import time
from pathlib import Path
from typing import Any, Callable

from .. import constants, paths
from ..logger import get_logger
from .lpk import LpkLoader
from .setup_model import MODEL_JSON_PATTERN, SetupModel

_log = get_logger("live2d")

#: 归一化后的模型名（与 app.config 的 pet.model 默认值保持一致）
MODEL_NAME = "HEI4.0"
#: 远端模型包地址（``/static/live2d/HEI.lpk`` 拼成绝对地址）
LPK_URL = constants.absolute(constants.REMOTE_LPK)

ProgressCallback = Callable[[int, int], None]
LogCallback = Callable[[str, str], None]
DownloadCallback = Callable[..., Any]

_LOG_METHODS = {
    "DEBUG": "debug",
    "INFO": "info",
    "WARNING": "warning",
    "ERROR": "error",
    "CRITICAL": "critical",
}


class LPKError(Exception):
    """模型包下载 / 解包 / 归一化失败；``str(exc)`` 是可直接展示的中文原因。"""


class Live2DProvider:
    """负责：下载 HEI.lpk → 解密解包 → 归一化 → 缓存，全部落在 ~/.Cr/forum/Live2D/ 下。"""

    def __init__(self, data_dir: str | Path | None = None,
                 downloader: DownloadCallback | None = None,
                 model: str | None = None) -> None:
        """
        :param data_dir: 数据根目录覆盖（测试用，默认 ``~/.Cr/forum``）
        :param downloader: 可注入的下载实现
            ``downloader(url, dest: Path, on_progress) -> (ok: bool, msg: str)``；
            默认用 :class:`app.api.ForumApi`
        :param model: 模型版本号（``1.1`` / ``2.3`` / ``3.0.1`` / ``3.0.2`` / ``4.0``），
            默认 :data:`app.constants.LIVE2D_MODEL_DEFAULT`；``"HEI4.0"`` 等旧写法会被归一化
        """
        self._data_dir = Path(data_dir).expanduser() if data_dir else None
        self._downloader = downloader
        self._spec = constants.live2d_model(model)
        self.key = str(self._spec["key"])
        self.model_name = str(self._spec["name"])
        self.lpk_name = str(self._spec["lpk_name"])

    # ────────────────── 版本 ──────────────────

    @property
    def spec(self) -> dict:
        """当前模型版本的元数据（见 :data:`app.constants.LIVE2D_MODELS`）。"""
        return self._spec

    @staticmethod
    def list_models() -> tuple:
        """全部可选的模型版本元数据。"""
        return constants.LIVE2D_MODELS

    def lpk_urls(self) -> tuple:
        """候选下载地址（按顺序尝试；首个为主链接）。"""
        urls: list[str] = []
        for remote in (self._spec.get("remotes") or ()):
            url = constants.absolute(remote)
            if url and url not in urls:
                urls.append(url)
        return tuple(urls)

    @property
    def lpk_url(self) -> str:
        """主下载地址。"""
        urls = self.lpk_urls()
        return urls[0] if urls else LPK_URL

    # ────────────────── 路径 ──────────────────

    @property
    def root_dir(self) -> Path:
        """Live2D 缓存根目录（默认 ``~/.Cr/forum/Live2D``）。"""
        if self._data_dir is not None:
            return self._data_dir / paths.live2d_dir().name
        return paths.live2d_dir()

    @property
    def lpk_path(self) -> Path:
        """模型包路径：``<root>/<lpk_name>``（默认 4.0 为 ``<root>/HEI.lpk``）。"""
        return self.root_dir / self.lpk_name

    @property
    def tmp_dir(self) -> Path:
        """解包中间产物目录：``<root>/tmp``（用完即删）。"""
        return self.root_dir / "tmp"

    @property
    def unpack_dir(self) -> Path:
        """解包输出目录：``<root>/tmp/unpack``。"""
        return self.tmp_dir / "unpack"

    @property
    def model_dir(self) -> Path:
        """归一化后的模型目录：``<root>/<model_name>``（默认 ``<root>/HEI4.0``）。"""
        return self.root_dir / self.model_name

    @property
    def model_json(self) -> Path:
        """归一化后的 ``.model3.json``（默认 ``<root>/HEI4.0/HEI4.0.model3.json``）。"""
        return self.model_dir / (self.model_name + ".model3.json")

    @property
    def pointer_path(self) -> Path:
        """指针文件：``app.paths.live2d_model_json_path()``（默认 ``<root>/model.json``）。"""
        if self._data_dir is not None:
            return self.root_dir / paths.live2d_model_json_path().name
        return paths.live2d_model_json_path()

    # ────────────────── 状态 ──────────────────

    def is_ready(self) -> bool:
        """``model_json`` 存在且能解析为 JSON 对象。"""
        path = self.model_json
        try:
            if not path.is_file():
                return False
            with open(path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
        except (OSError, ValueError):
            return False
        return isinstance(data, dict)

    def info(self) -> dict:
        """当前缓存概览（只做只读检查，不会触发下载/解包）。"""
        try:
            size = int(self.lpk_path.stat().st_size) if self.lpk_path.is_file() else 0
        except OSError:
            size = 0
        meta = self._read_pointer()
        model_ok = self.is_ready()
        return {
            "lpk": self.lpk_path.is_file(),
            "size": size,
            "model": model_ok,
            "model_key": self.key,
            "model_name": self.model_name,
            "lpk_name": self.lpk_name,
            "model_json": str(self.model_json) if model_ok else "",
            "model_dir": str(self.model_dir),
            "lpk_path": str(self.lpk_path),
            "pointer": str(self.pointer_path) if self.pointer_path.is_file() else "",
            "unpacked_at": meta.get("unpacked_at"),
        }

    # ────────────────── 主流程 ──────────────────

    def ensure(self, on_progress: ProgressCallback | None = None,
               on_log: LogCallback | None = None, force: bool = False) -> Path:
        """幂等地准备好模型，返回归一化后的 ``.model3.json`` 路径。

        缺 lpk 就下载（只下一次，之后复用缓存）；缺 model 就解包 + 归一化。
        失败抛 :class:`LPKError`（带中文原因）。
        """
        if not force and self.is_ready():
            self._emit(on_log, "INFO", "模型已缓存，直接复用：%s" % self.model_json)
            return self.model_json

        try:
            self.root_dir.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise LPKError("无法创建数据目录（%s）：%s" % (self.root_dir, exc)) from exc

        # 1) 模型包：缺才下载
        if force or not self._lpk_cached():
            urls = self.lpk_urls() or (LPK_URL,)
            self._emit(on_log, "INFO", "开始下载模型包（%s）：%s" % (self.key, urls[0]))
            ok, msg = False, ""
            for index, url in enumerate(urls):
                ok, msg = self._download(url, self.lpk_path, on_progress)
                if ok and self._lpk_cached():
                    break
                if index + 1 < len(urls):
                    self._emit(on_log, "WARNING", "下载源不可用，尝试下一个：%s" % url)
            if not ok:
                raise LPKError("模型包下载失败：%s" % (msg or "未知原因"))
            if not self._lpk_cached():
                raise LPKError("模型包下载失败：文件为空（%s）" % self.lpk_path)
            self._emit(on_log, "INFO", "模型包已就绪：%s（%d 字节）"
                       % (self.lpk_path, self.lpk_path.stat().st_size))
        else:
            self._emit(on_log, "INFO", "复用已缓存的模型包：%s" % self.lpk_path)

        # 2) 解包 + 归一化
        json_path = self._build(on_log)
        # 3) 写指针文件（记录当前模型与解包时间）
        self._write_pointer(json_path)
        self._emit(on_log, "INFO", "模型准备完成：%s" % json_path)
        return json_path

    def clear_cache(self, *, keep_lpk: bool = True, all_models: bool = False) -> None:
        """清掉模型目录与解包中间产物。

        * ``keep_lpk=False``：连当前模型的模型包一起删
        * ``all_models=True``：把**所有**版本的模型目录与模型包一并清掉
        """
        if all_models:
            for spec in constants.LIVE2D_MODELS:
                shutil.rmtree(self.root_dir / spec["name"], ignore_errors=True)
                self._unlink(self.root_dir / spec["lpk_name"])
            shutil.rmtree(self.tmp_dir, ignore_errors=True)
            self._unlink(self.pointer_path)
            return
        shutil.rmtree(self.model_dir, ignore_errors=True)
        shutil.rmtree(self.tmp_dir, ignore_errors=True)
        self._unlink(self.pointer_path)
        if not keep_lpk:
            self._unlink(self.lpk_path)

    @staticmethod
    def _unlink(path: Path) -> None:
        try:
            path.unlink()
        except OSError:
            pass

    # ────────────────── 内部实现 ──────────────────

    def _lpk_cached(self) -> bool:
        try:
            return self.lpk_path.is_file() and self.lpk_path.stat().st_size > 0
        except OSError:
            return False

    def _build(self, on_log: LogCallback | None) -> Path:
        """解包 → 归一化；无论成败都清掉 ``tmp/``。"""
        try:
            shutil.rmtree(self.tmp_dir, ignore_errors=True)
            self.unpack_dir.mkdir(parents=True, exist_ok=True)
            self._emit(on_log, "INFO", "解密解包：%s" % self.lpk_path)
            loader = LpkLoader(self.lpk_path, None)
            try:
                subdirs = loader.extract(str(self.unpack_dir))
            finally:
                loader.close()
            source = self._find_model_source(self.unpack_dir, subdirs)
            self._emit(on_log, "INFO", "归一化：%s → %s" % (source, self.model_dir))
            shutil.rmtree(self.model_dir, ignore_errors=True)
            json_path = SetupModel(source, self.model_dir, self.model_name, cleanup_source=False)
            if not json_path.is_file():
                raise LPKError("归一化失败：没有生成 %s" % json_path)
            return json_path
        except LPKError:
            raise
        except Exception as exc:
            raise LPKError("解包/归一化失败：%s" % exc) from exc
        finally:
            shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def _find_model_source(self, unpack: Path, subdirs: list[str] | None) -> Path:
        """在解包输出里找出含 ``modelN.json`` 的角色目录。"""
        candidates: list[Path] = []
        for sub in (subdirs or []):
            p = Path(sub)
            if p.is_dir():
                candidates.append(p)
        if not candidates and unpack.is_dir():
            candidates = [p for p in sorted(unpack.iterdir()) if p.is_dir()]
        for cand in candidates:
            try:
                for entry in cand.iterdir():
                    if entry.is_file() and MODEL_JSON_PATTERN.match(entry.name):
                        return cand
            except OSError:
                continue
        if candidates:
            return candidates[0]
        raise LPKError("解包后在 %s 里找不到角色目录" % unpack)

    def _download(self, url: str, dest: Path,
                  on_progress: ProgressCallback | None) -> tuple[bool, str]:
        """执行下载；返回 ``(ok, 失败原因)``。"""
        if self._downloader is not None:
            try:
                ok, msg = self._downloader(url, dest, on_progress)
            except Exception as exc:
                return False, str(exc)
            return bool(ok), str(msg or "")
        try:
            from ..api import ForumApi
        except Exception as exc:
            return False, "无法加载下载模块 app.api：%s" % exc
        try:
            result = ForumApi().download(url, dest, on_progress=on_progress)
        except Exception as exc:
            return False, str(exc)
        return bool(result.ok), str(result.message or "")

    def _read_pointer(self) -> dict:
        try:
            with open(self.pointer_path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
        except (OSError, ValueError):
            return {}
        return data if isinstance(data, dict) else {}

    def _write_pointer(self, model_json: Path) -> None:
        payload = {
            "kind": "live2d-model-pointer",
            "model": self.model_name,
            "model_key": self.key,
            "model_dir": self.model_dir.name,
            "model3": str(model_json),
            "lpk": self.lpk_path.name,
            "lpk_size": self.info().get("size", 0),
            "unpacked_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "unpacked_at_ts": time.time(),
        }
        try:
            self.pointer_path.parent.mkdir(parents=True, exist_ok=True)
            self.pointer_path.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
            _log.info("模型指针已写入：%s", self.pointer_path)
        except OSError as exc:
            _log.warning("写入模型指针文件失败：%s", exc)

    def _emit(self, on_log: LogCallback | None, level: str, text: str) -> None:
        """同时打给日志器和调用方的 ``on_log`` 回调。"""
        try:
            getattr(_log, _LOG_METHODS.get(str(level).upper(), "info"))("%s", text)
        except Exception:
            pass
        if on_log is not None:
            try:
                on_log(str(level).upper(), text)
            except Exception:
                pass


# ────────────────────────── 命令行验收入口 ──────────────────────────


def _format_size(num: int) -> str:
    """人类可读的字节数。"""
    try:
        value = float(num)
    except (TypeError, ValueError):
        return "未知"
    for unit in ("B", "KB", "MB", "GB"):
        if value < 1024 or unit == "GB":
            return ("%d %s" % (int(value), unit)) if unit == "B" else ("%.2f %s" % (value, unit))
        value /= 1024.0
    return "%.2f GB" % value


def _print_tree(root: Path, limit: int = 30) -> None:
    """打印目录树的前 ``limit`` 项。"""
    lines: list[str] = []

    def walk(directory: Path, prefix: str) -> None:
        try:
            entries = sorted(directory.iterdir(),
                             key=lambda p: (p.is_file(), p.name.lower()))
        except OSError:
            return
        for entry in entries:
            if len(lines) >= limit:
                return
            lines.append("%s%s%s" % (prefix, entry.name, "/" if entry.is_dir() else ""))
            if entry.is_dir() and len(lines) < limit:
                walk(entry, prefix + "    ")

    walk(root, "")
    print("目录树（%s，共展示 %d 项）：" % (root.name, len(lines)))
    for line in lines:
        print("  " + line)


def _cli(argv: list[str] | None = None) -> int:
    """``python -m app.live2d.provider`` 的入口（真实下载 + 解包一次）。"""
    import argparse

    parser = argparse.ArgumentParser(description="下载并解包 Live2D 模型（HEI.lpk）")
    parser.add_argument("--data-dir", default=None,
                        help="覆盖数据目录（默认取 CRFORUM_DATA_DIR 或 ~/.Cr/forum）")
    parser.add_argument("--force", action="store_true", help="忽略缓存，强制重新下载并解包")
    parser.add_argument("--model", default=None,
                        help="模型版本号（1.1 / 2.3 / 3.0.1 / 3.0.2 / 4.0，默认 4.0）")
    parser.add_argument("--tree", type=int, default=30, help="目录树展示条目数（默认 30）")
    args = parser.parse_args(argv)

    provider = Live2DProvider(data_dir=args.data_dir, model=args.model)
    print("模型版本：%s（%s）" % (provider.key, provider.spec.get("note") or ""))
    print("模型包地址：%s" % provider.lpk_url)
    print("缓存根目录：%s" % provider.root_dir)
    print("模型目录：%s" % provider.model_dir)

    last = [0.0]

    def on_progress(done: int, total: int) -> None:
        if total:
            pct = done * 100.0 / total
            if pct - last[0] >= 10 or done >= total:
                last[0] = pct
                print("  下载中：%d / %d 字节（%.1f%%）" % (done, total, pct))
        elif done - last[0] >= 256 * 1024:
            last[0] = float(done)
            print("  下载中：%d 字节" % done)

    started = time.time()
    try:
        json_path = provider.ensure(
            on_progress=on_progress,
            on_log=lambda level, text: print("[%s] %s" % (level, text)),
            force=args.force,
        )
    except LPKError as exc:
        print("失败：%s" % exc)
        return 1
    print("耗时：%.1f 秒" % (time.time() - started))

    info = provider.info()
    print("info()：")
    for key in ("lpk", "size", "model", "model_json", "model_dir", "pointer", "unpacked_at"):
        value = info.get(key)
        if key == "size":
            value = "%s（%s）" % (value, _format_size(int(value or 0)))
        print("  %-11s %s" % (key, value))

    print("model_json：%s" % json_path)
    _print_tree(provider.root_dir, max(1, args.tree))

    try:
        data = json.loads(Path(json_path).read_text(encoding="utf-8"))
        print("model3.json 顶层键：%s" % ", ".join(sorted(data.keys())))
        refs = data.get("FileReferences") or {}
        print("FileReferences 键：%s" % ", ".join(sorted(refs.keys())))
        motions = refs.get("Motions") or {}
        total = sum(len(v or []) for v in motions.values() if isinstance(v, list))
        print("动作组：%s（共 %d 个动作）" % (", ".join(sorted(motions.keys())), total))
    except Exception as exc:
        print("读取 model3.json 失败：%s" % exc)
    return 0


if __name__ == "__main__":
    raise SystemExit(_cli())
