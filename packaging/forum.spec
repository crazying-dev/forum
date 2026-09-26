# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller 备用打包配置（主用 Nuitka，见 build.ps1）。

特点：

* ``--onedir``：**不使用单文件**，exe 与依赖分散在一个目录里
* 不启用 UPX（避免部分杀软误报），保留 DLL 原状
* 把 ``live2d-py`` 的原生库完整收集进去（它是桌宠能跑起来的前提）
* 打包后目录结构：``forum.exe`` + ``_internal/``（含 ``resources/``）

使用：``pyinstaller --noconfirm --clean packaging/forum.spec``
"""

import os
import sys

from PyInstaller.utils.hooks import collect_all

# PyInstaller 把 SPECPATH 设为 **本 spec 文件所在的目录**（即 packaging/），
# 因此仓库根目录是它的上一级；不要再套一层 dirname（否则会跑到仓库外面去）。
ROOT = os.path.abspath(os.path.join(SPECPATH, ".."))

binaries = []
datas = [(os.path.join(ROOT, "resources"), "resources")]
hiddenimports = []

for package in ("live2d",):
    try:
        pkg_datas, pkg_binaries, pkg_hidden = collect_all(package)
        datas += pkg_datas
        binaries += pkg_binaries
        hiddenimports += pkg_hidden
    except Exception as exc:  # noqa: BLE001
        print("[forum.spec] 收集 %s 失败：%s" % (package, exc))

hiddenimports += [
    "PyQt6.QtNetwork",
    "PyQt6.QtSvg",
    "app.api",
    "app.deeplink",
    "app.tray",
    "app.updater",
    "app.autostart",
]

a = Analysis(
    [os.path.join(ROOT, "main.py")],
    pathex=[ROOT],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=[
        "tkinter",
        "_tkinter",
        "matplotlib",
        "scipy",
        "pandas",
        "IPython",
        "pytest",
        "PIL",
    ],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="forum",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    icon=os.path.join(ROOT, "resources", "icon", "icon.ico"),
    version=os.path.join(SPECPATH, "version_info.txt"),
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="forum",
)
