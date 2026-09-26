# -*- coding: utf-8 -*-
"""LPK 解包器（移植自 ``lpk2moc3/Core/lpk_loader.py``）。

与原实现的**有意差异**：

* 日志改用 ``app.logger``，并去掉 ``import manager``（那是界面模块）；
* ``extract(outputdir)`` 用 ``os.makedirs(..., exist_ok=True)``，父目录不存在时不再抛异常；
* ``configpath`` 改为可选：只有 Steam 创意工坊包（``STM_1_0``）才需要 config.json；
* 读 ``config.mlve`` 时多一层「明文条目名」回退（部分早期/非 Steam 的包不经 md5 命名）；
* 角色目录名做 Windows 文件名净化（``pack_utils.normalize``）；
* ``check_decrypt()`` 不再读 STDIN（桌面端不能阻塞），只记日志；
* ``extract()`` 返回实际生成的子目录列表，方便调用方定位模型目录；
* 不依赖 ``chardet``（原实现 import 了却没用）。
"""

from __future__ import annotations

import json
import os
import zipfile

from ..logger import get_logger
from .pack_utils import (
    decrypt,
    genkey,
    get_encrypted_file,
    guess_type,
    hashed_filename,
    normalize,
    travels_dict,
)

_log = get_logger("live2d.lpk")

#: LPK 容器类型
TYPE_STD2_0 = "STD2_0"
TYPE_STM_1_0 = "STM_1_0"


class LpkLoader:
    """Live2DViewerEX 的 ``.lpk`` 解包器。"""

    def __init__(self, lpkpath: str | os.PathLike,
                 configpath: str | os.PathLike | None = None) -> None:
        self.lpkpath = str(lpkpath)
        self.configpath = str(configpath) if configpath else None
        self.lpkType = ""
        self.mlve_config: dict = {}
        self.config: dict = {}
        #: 加密条目名 → 解密后的文件名
        self.trans: dict[str, str] = {}
        #: 解密后的 modelN.json 内容（键为 modelN.json）
        self.entrys: dict[str, str] = {}
        self.lpkfile: zipfile.ZipFile | None = None
        self.load_lpk()

    # ────────────────── 加载 ──────────────────

    def load_lpk(self) -> None:
        try:
            self.lpkfile = zipfile.ZipFile(self.lpkpath)
        except (OSError, zipfile.BadZipFile) as exc:
            raise ValueError("不是有效的 LPK(zip) 文件：%s（%s）" % (self.lpkpath, exc)) from exc

        self.mlve_config = self._read_mlve_config()
        self.lpkType = str(self.mlve_config.get("type") or "")
        _log.debug("LPK 类型：%s", self.lpkType or "未知")

        # 只有 Steam 创意工坊的 lpk 需要 config.json 才能解密
        if self.lpkType == TYPE_STM_1_0:
            self.load_config()

    def _read_mlve_config(self) -> dict:
        """读 lpk 内的 ``config.mlve``（优先 md5 条目名，退回明文条目名）。"""
        assert self.lpkfile is not None
        for name in (hashed_filename("config.mlve"), "config.mlve"):
            try:
                raw = self.lpkfile.read(name)
            except KeyError:
                continue
            try:
                text = raw.decode("utf-8-sig")
            except UnicodeDecodeError as exc:
                raise ValueError("config.mlve 不是文本，可能是不支持的 LPK 格式") from exc
            try:
                return json.loads(text)
            except ValueError as exc:
                raise ValueError("config.mlve 解析失败：%s" % exc) from exc
        raise ValueError("LPK 内找不到 config.mlve，无法解包")

    def load_config(self) -> None:
        if not self.configpath:
            raise ValueError("该 LPK 是 Steam 创意工坊格式（STM_1_0），必须提供 config.json")
        try:
            with open(self.configpath, "r", encoding="utf8") as fh:
                self.config = json.load(fh)
        except (OSError, ValueError) as exc:
            raise ValueError("config.json 读取失败：%s" % exc) from exc

    def close(self) -> None:
        if self.lpkfile is not None:
            try:
                self.lpkfile.close()
            except Exception:
                pass
            self.lpkfile = None

    # ────────────────── 解包 ──────────────────

    def extract(self, outputdir: str | os.PathLike) -> list[str]:
        """把整个 lpk 解到 ``outputdir``，返回实际生成的子目录列表。"""
        outputdir = str(outputdir)
        # 原实现用 os.mkdir，父目录不存在会直接报错
        os.makedirs(outputdir, exist_ok=True)
        created: list[str] = []

        for chara in self.mlve_config.get("list") or []:
            chara_name = chara.get("character") or "character"
            subdir = os.path.join(outputdir, normalize(str(chara_name)))
            os.makedirs(subdir, exist_ok=True)
            created.append(subdir)

            costumes = chara.get("costume") or []
            for i in range(len(costumes)):
                _log.info("解包 %s 的第 %d 套服装", chara_name, i)
                self.extract_costume(costumes[i], subdir)

            # 把 model.json 里被加密的文件名替换成解密后的文件名
            for name in self.entrys:
                out_s = self.entrys[name]
                for k in self.trans:
                    out_s = out_s.replace(k, self.trans[k])
                with open(os.path.join(subdir, name), "w", encoding="utf8") as fh:
                    fh.write(out_s)
        return created

    def extract_costume(self, costume: dict, outdir: str) -> None:
        path = costume.get("path") if isinstance(costume, dict) else None
        if not path:
            return
        self.check_decrypt(path)
        self.extract_model_json(path, outdir)

    def extract_model_json(self, model_json: str, outdir: str) -> None:
        # 同一个模型 json 只解一次（change_cos 可能被多个服装引用）
        if model_json in self.trans:
            return

        entry_s = self.decrypt_file(model_json).decode("utf-8")
        entry = json.loads(entry_s)

        out_s = json.dumps(entry, ensure_ascii=False)
        id = len(self.entrys)

        self.entrys["model%d.json" % id] = out_s
        self.trans[model_json] = "model%d.json" % id

        for name, val in travels_dict(entry):
            enc_file = get_encrypted_file(val)
            if not enc_file:
                continue
            # 已经解过
            if enc_file in self.trans:
                continue
            # 子模型（换装）
            if str(val).startswith("change_cos"):
                self.extract_model_json(enc_file, outdir)
            # 普通资源
            else:
                name += "_%d" % id
                _, suffix = self.recovery(enc_file, os.path.join(outdir, name))
                self.trans[enc_file] = name + suffix

    # ────────────────── 解密 ──────────────────

    def check_decrypt(self, filename: str) -> None:
        """确认解密可用。

        若 lpk 在 config.json 里抹掉了 fileId，这里会自动尝试用 lpkFile 当 fileId；
        全部失败时只记日志（原实现在此处读 STDIN，桌面端无法这样做）。
        """
        _log.debug("尝试解密入口模型：%s", filename)
        try:
            self.decrypt_file(filename).decode(encoding="utf8")
            return
        except UnicodeDecodeError:
            pass

        _log.info("尝试自动修正 fileId")
        success = False
        lpk_file = (self.config or {}).get("lpkFile")
        if lpk_file:
            for fileid in [str(lpk_file).strip(".lpk")]:
                self.config["fileId"] = fileid
                try:
                    self.decrypt_file(filename).decode(encoding="utf8")
                except UnicodeDecodeError:
                    continue
                success = True
                break
        if not success:
            _log.error(
                "自动修正 fileId 失败；Steam 创意工坊的 fileId 通常是 "
                "steamapps/workshop/content/616720/<数字> 这一级目录名，"
                "请在 config.json 里补全 fileId")

    def recovery(self, filename: str, output: str) -> tuple[bytes, str]:
        """解密资源并写盘（扩展名由内容猜），返回 ``(内容, 后缀)``。"""
        ret = self.decrypt_file(filename)
        suffix = guess_type(ret)
        target = output + suffix
        if not suffix:
            _log.warning("无法识别资源类型，按无扩展名写出：%s", filename)
        folder = os.path.dirname(target)
        if folder:
            os.makedirs(folder, exist_ok=True)
        with open(target, "wb") as fh:
            fh.write(ret)
        _log.info("[LPK Loader]: recovering %s -> %s", filename, target)
        return ret, suffix

    def getkey(self, file: str) -> int:
        lpk_type = self.lpkType
        encrypt = str(self.mlve_config.get("encrypt", "true"))
        if lpk_type == TYPE_STM_1_0 and encrypt != "true":
            return 0
        if lpk_type == TYPE_STM_1_0:
            return genkey(str(self.mlve_config["id"]) + str(self.config["fileId"])
                          + file + str(self.config["metaData"]))
        if lpk_type == TYPE_STD2_0:
            return genkey(str(self.mlve_config["id"]) + file)
        raise ValueError("不支持的 LPK 类型：%s" % (lpk_type or "<空>"))

    def decrypt_file(self, filename: str) -> bytes:
        if self.lpkfile is None:
            raise ValueError("LPK 未打开")
        data = self.lpkfile.read(filename)
        return self.decrypt_data(filename, data)

    def decrypt_data(self, filename: str, data: bytes) -> bytes:
        key = self.getkey(filename)
        return decrypt(key, data)
