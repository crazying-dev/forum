# -*- coding: utf-8 -*-
"""模型归一化（移植自 ``lpk2moc3/manager.py`` 的 ``CheckPath`` / ``SetupModel``）。

把 ``LpkLoader`` 解出来的「一坨散装文件」整理成 live2d-py 能直接加载的目录结构::

    <target_dir>/
    ├── <modelName>.model3.json
    ├── motions/<modelName>_<group>.motion3.json
    ├── sounds/*.wav               （有音频且本机有 ffmpeg 时）
    └── FileReferences_*           （纹理 / .moc3 / 表情 / 物理 / Pose 等）

与原实现的**有意差异**：

* 去掉 tkinter 与全局 ``LogArea``，日志改用 ``app.logger``；
* **不再做破坏性的 ``os.rename``**：归一化结果写到调用方给的 ``target_dir``，
  源目录默认原样保留（``cleanup_source=False``），解包中间产物可以复用/复盘；
* 因此必须把源目录里所有 ``FileReferences_*`` 资源复制到 ``target_dir``，
  否则 ``<modelName>.model3.json`` 的相对引用会失效；
* ffmpeg 只做「有则转换、无则跳过」：找不到可执行文件时 warning 并跳过 Sound；
* 返回生成的 ``.model3.json`` 的绝对路径（``pathlib.Path``）。
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from pathlib import Path

from .. import paths
from ..logger import get_logger
from . import motion_spec

_log = get_logger("live2d.setup")

#: 解包器写出的模型配置文件名：model.json / model0.json ... model9.json
MODEL_JSON_PATTERN = re.compile(r"^model\d?\.json$")
#: 解包器给资源文件加的前缀（模型 json 用该前缀做相对引用）
RESOURCE_PREFIX = "FileReferences"
#: ffmpeg 单次转换超时（秒）
FFMPEG_TIMEOUT = 120


def rmdir(path: str | os.PathLike) -> None:
    """递归删除目录（沿用原实现的名字）；不存在时静默返回。"""
    shutil.rmtree(path, ignore_errors=True)


def find_ffmpeg() -> str | None:
    """按 ``resources/ffmpeg/bin`` → 环境变量 ``FFMPEG`` → PATH 的顺序找 ffmpeg。"""
    candidates: list[Path] = [
        Path(paths.resource("ffmpeg", "bin", "ffmpeg.exe")),
        Path(paths.resource("ffmpeg", "bin", "ffmpeg")),
    ]
    env = os.environ.get("FFMPEG")
    if env:
        candidates.append(Path(env))
    for cand in candidates:
        try:
            if cand.is_file():
                return str(cand)
        except OSError:
            continue
    return shutil.which("ffmpeg")


def CheckPath(model_dir: str | os.PathLike) -> tuple[Path, Path]:
    """确保 ``motions/`` 与 ``sounds/`` 存在，返回两者路径。"""
    motionPath = Path(model_dir) / "motions"
    soundPath = Path(model_dir) / "sounds"
    motionPath.mkdir(parents=True, exist_ok=True)
    soundPath.mkdir(parents=True, exist_ok=True)
    return motionPath, soundPath


def SetupModel(model_dir: str | os.PathLike, target_dir: str | os.PathLike,
               modelNameBase: str | None = None,
               cleanup_source: bool = False) -> Path:
    """把 ``model_dir`` 里解包好的散装文件归一化到 ``target_dir``。

    :param model_dir: ``LpkLoader.extract()`` 的输出目录（内含 modelN.json）
    :param target_dir: 归一化输出目录（会被创建/覆盖同名文件）
    :param modelNameBase: 模型名，默认取源目录名；用于动作文件名与 <名>.model3.json
    :param cleanup_source: 成功后是否删掉源目录（默认 False，保留解包缓存）
    :return: 生成的 ``.model3.json`` 绝对路径
    """
    source = Path(model_dir)
    target = Path(target_dir)
    if not source.is_dir():
        raise FileNotFoundError("源模型目录不存在：%s" % source)

    motionPath, soundPath = CheckPath(target)
    if not modelNameBase:
        modelNameBase = source.name
    modelNameBase = str(modelNameBase)

    modelJsonPathList: list[Path] = []
    for entry in sorted(source.iterdir()):
        if entry.is_file() and MODEL_JSON_PATTERN.match(entry.name):
            modelJsonPathList.append(entry)
    if not modelJsonPathList:
        raise FileNotFoundError("在 %s 里找不到 model\\d?.json，解包可能失败" % source)
    _log.info("Model Json Found: %s", [p.name for p in modelJsonPathList])

    ffmpeg = find_ffmpeg()
    if ffmpeg is None:
        _log.warning("没找到 ffmpeg，本次跳过音频（Sound）处理；可用 FFMPEG 环境变量指定")
    else:
        _log.debug("ffmpeg: %s", ffmpeg)

    consumed: list[Path] = []
    first_json: Path | None = None
    for idx, modelJsonPath in enumerate(modelJsonPathList):
        # 与原实现一致：第 1 个用原名字，之后的加序号
        modelName = modelNameBase + ("" if idx == 0 else str(idx + 1))
        outJson = _normalize_one(source, target, modelJsonPath, modelName,
                                 motionPath, soundPath, ffmpeg, consumed)
        if first_json is None:
            first_json = outJson

    copied = _copy_resources(source, target)
    _log.info("复制资源 %d 个 → %s", copied, target)

    if cleanup_source:
        _log.info("按需清理源目录：%s", source)
        rmdir(source)
    else:
        _log.debug("保留源目录（已消费 %d 个文件）：%s", len(consumed), source)

    if first_json is None:  # pragma: no cover - 前面已保证非空
        raise FileNotFoundError("归一化没有产出任何 .model3.json")
    return first_json


def _normalize_one(source: Path, target: Path, modelJsonPath: Path, modelName: str,
                   motionPath: Path, soundPath: Path, ffmpeg: str | None,
                   consumed: list[Path]) -> Path:
    """归一化单个 modelN.json，返回写出的 ``<modelName>.model3.json``。"""
    try:
        with open(modelJsonPath, "r", encoding="utf-8") as fh:
            x = json.load(fh)
    except (OSError, ValueError) as exc:
        raise ValueError("%s 解析失败：%s" % (modelJsonPath.name, exc)) from exc

    fileRefs = x.get("FileReferences")
    if not isinstance(fileRefs, dict):
        raise ValueError("%s 里缺少 FileReferences" % modelJsonPath.name)

    motions = fileRefs.get("Motions") or {}
    for groupName in motions:
        _log.info("[Motion Group]: %s", groupName)
        group = motions[groupName] or []
        for motion in group:
            if not isinstance(motion, dict):
                continue
            _File = motion.get("File")
            _Sound = motion.get("Sound")
            # motions/*.motion3.json
            if _File:
                srcPath = source / _File
                fileName = (_File.replace("FileReferences_Motions", modelName)
                            .replace("_File_0", "").replace(".json", ".motion3.json"))
                if not srcPath.is_file():
                    _log.warning("动作文件缺失，跳过：%s", srcPath)
                else:
                    targetPath = motionPath / fileName
                    _write_motion(srcPath, targetPath)
                    consumed.append(srcPath)
                    motion["File"] = "motions/" + fileName
                    _log.info("[Motion]: %s >>> %s", _File, targetPath)
            # sounds/*.wav
            if _Sound:
                srcPath = source / _Sound
                fileName = (_Sound.replace("FileReferences_Motions", modelName)
                            .replace("_Sound_0", ""))
                fileName = os.path.splitext(fileName)[0] + ".wav"
                targetPath = soundPath / fileName
                if ffmpeg is None:
                    _log.warning("缺少 ffmpeg，跳过音频：%s", _Sound)
                elif not srcPath.is_file():
                    _log.warning("音频文件缺失，跳过：%s", srcPath)
                elif _convert_audio(ffmpeg, srcPath, targetPath):
                    consumed.append(srcPath)
                    motion["Sound"] = "sounds/" + fileName
                    _log.info("[Sound]: %s >>> %s", _Sound, targetPath)

    # 把 hitAreas 与动作组 / 控制器关联起来
    hitAreas = x.get("HitAreas")
    if not isinstance(hitAreas, list):
        hitAreas = []
        x["HitAreas"] = hitAreas
    for idx2, hitArea in enumerate(hitAreas):
        if isinstance(hitArea, dict) and hitArea.get("Motion") is not None:
            hitAreas[idx2]["Name"] = str(hitArea["Motion"]).split(":")[0]

    controllers = x.get("Controllers")
    if isinstance(controllers, dict) and isinstance(controllers.get("ParamHit"), dict):
        items = controllers["ParamHit"].get("Items")
        if isinstance(items, list):
            for item in items:
                if isinstance(item, dict) and item.get("EndMtn") is not None:
                    hitAreas.append({"Name": item.get("EndMtn"), "Id": item.get("Id")})

    # 写出 <modelName>.model3.json
    target.mkdir(parents=True, exist_ok=True)
    outJson = target / (modelName + ".model3.json")
    with open(outJson, "w", encoding="utf-8") as fh:
        json.dump(x, fh, ensure_ascii=False, indent=2)
    _log.info("[Model]: %s >>> %s", modelJsonPath.name, outJson)
    return outJson.resolve()


def _write_motion(srcPath: Path, targetPath: Path) -> None:
    """重算 CurveCount / TotalSegmentCount / TotalPointCount 后写出 motion3.json。"""
    with open(srcPath, "r", encoding="utf-8") as fh:
        src = json.load(fh)
    curve_count, segment_count, point_count = motion_spec.recount_motion(src)
    meta = src.setdefault("Meta", {})
    _log.debug("CurveCount: %s → %d", meta.get("CurveCount"), curve_count)
    _log.debug("TotalSegmentCount: %s → %d", meta.get("TotalSegmentCount"), segment_count)
    _log.debug("TotalPointCount: %s → %d", meta.get("TotalPointCount"), point_count)
    meta["CurveCount"] = curve_count
    meta["TotalSegmentCount"] = segment_count
    meta["TotalPointCount"] = point_count
    targetPath.parent.mkdir(parents=True, exist_ok=True)
    with open(targetPath, "w", encoding="utf-8") as fh:
        json.dump(src, fh, ensure_ascii=False, indent=2)


def _convert_audio(ffmpeg: str, srcPath: Path, targetPath: Path) -> bool:
    """用 ffmpeg 转成单声道 wav；失败只记 warning，返回是否成功。"""
    targetPath.parent.mkdir(parents=True, exist_ok=True)
    cmd = [ffmpeg, "-i", str(srcPath), "-ac", "1", str(targetPath), "-y", "-v", "quiet"]
    try:
        proc = subprocess.run(cmd, capture_output=True, timeout=FFMPEG_TIMEOUT)
    except (OSError, subprocess.SubprocessError) as exc:
        _log.warning("音频转换失败（%s）：%s", srcPath.name, exc)
        return False
    if proc.returncode != 0:
        detail = (proc.stderr or b"").decode("gbk", "replace").strip()
        _log.warning("ffmpeg 返回码 %d：%s", proc.returncode, detail)
        return False
    return targetPath.is_file()


def _copy_resources(source: Path, target: Path) -> int:
    """把源目录里所有 ``FileReferences_*`` 资源复制到 target（模型 json 按此名字引用）。"""
    copied = 0
    for entry in sorted(source.iterdir()):
        if entry.is_dir():
            if entry.name not in ("motions", "sounds"):
                _log.warning("源目录里有未预期的子目录，已忽略：%s", entry.name)
            continue
        if not entry.name.startswith(RESOURCE_PREFIX):
            continue
        try:
            shutil.copy2(entry, target / entry.name)
            copied += 1
        except OSError as exc:
            _log.warning("复制资源失败（%s）：%s", entry.name, exc)
    return copied
