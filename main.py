# -*- coding: utf-8 -*-
"""妖精论坛 Windows 客户端 —— 程序入口。

职责：初始化环境（路径 / 日志 / OpenGL 格式）→ 单实例转发 → QApplication →
主题 → 主窗口 → 托盘 / 鼠标指针 / Live2D 桌宠 → 事件循环。

命令行：

* ``main.py``                   正常启动
* ``main.py --minimized``       启动后直接收进托盘
* ``main.py --debug``           控制台输出 DEBUG 日志
* ``main.py "Crforum://post/xxx"`` 深链直达
"""

from __future__ import annotations

import os
import sys

SERVER_NAME = "crforum-windows-single"


def _bootstrap_path() -> None:
    root = os.path.dirname(os.path.abspath(__file__))
    if root not in sys.path:
        sys.path.insert(0, root)


_bootstrap_path()

from PyQt6.QtGui import QFont, QIcon, QSurfaceFormat  # noqa: E402
from PyQt6.QtNetwork import QLocalServer, QLocalSocket  # noqa: E402
from PyQt6.QtWidgets import QApplication  # noqa: E402

from app import config as config_mod  # noqa: E402
from app import api as api_mod  # noqa: E402
from app import constants, deeplink, logger, paths, theme  # noqa: E402
from app.shell import Shell  # noqa: E402

_log = logger.get_logger("main")


# ────────────────────────── 环境 ──────────────────────────


def _set_surface_format() -> None:
    """设置默认 OpenGL 表面格式。

    **不要**指定 ``setVersion`` / ``setProfile``：Cubism 原生渲染器在某些驱动上
    遇到 3.3 Core/Compatibility 上下文会报 GL_INVALID_OPERATION（1282）
    并完全不输出像素（已实测）。交给驱动默认（本机为 4.6 CompatibilityProfile）
    则一切正常。这里只保留与桌宠透明 / 深度相关的配置。
    """
    fmt = QSurfaceFormat()
    fmt.setRenderableType(QSurfaceFormat.RenderableType.OpenGL)
    fmt.setDepthBufferSize(24)
    fmt.setStencilBufferSize(8)
    fmt.setAlphaBufferSize(8)
    fmt.setSwapBehavior(QSurfaceFormat.SwapBehavior.DoubleBuffer)
    QSurfaceFormat.setDefaultFormat(fmt)


def _setup_app(argv: list[str], debug: bool) -> QApplication:
    paths.ensure_dirs()
    logger.setup(level=10 if debug else 20)
    logger.hook_excepthook()
    _set_surface_format()

    app = QApplication(argv)
    app.setApplicationName(constants.APP_ID)
    app.setApplicationDisplayName(constants.APP_NAME)
    app.setOrganizationName("CrForum")
    app.setQuitOnLastWindowClosed(False)
    if constants.RES_ICON.is_file():
        app.setWindowIcon(QIcon(str(constants.RES_ICON)))
    app.setFont(QFont("Microsoft YaHei UI", 9))
    return app


# ────────────────────────── 单实例 ──────────────────────────


def _forward_to_existing(urls: list[str], *, minimized: bool = False) -> bool:
    """已有实例在跑 → 把深链/唤醒命令发过去并退出。"""
    socket = QLocalSocket()
    socket.connectToServer(SERVER_NAME)
    if not socket.waitForConnected(400):
        return False
    payload = " ".join(urls) if urls else "__wake__"
    try:
        socket.write(payload.encode("utf-8"))
        socket.flush()
        socket.waitForBytesWritten(400)
        socket.disconnectFromServer()
        if socket.state() != QLocalSocket.LocalSocketState.UnconnectedState:
            socket.waitForDisconnected(200)
    except Exception:
        pass
    _log.info("已把请求转发给运行中的实例：%s", payload)
    return True


def _start_single_instance_server(shell: Shell) -> QLocalServer | None:
    QLocalServer.removeServer(SERVER_NAME)
    server = QLocalServer()
    if not server.listen(SERVER_NAME):
        _log.warning("单实例服务启动失败：%s", server.errorString())
        return None

    def _on_new_connection() -> None:
        conn = server.nextPendingConnection()
        if conn is None:
            return
        state = {"data": b""}

        def _read() -> None:
            state["data"] += bytes(conn.readAll())

        def _finish() -> None:
            text = state["data"].decode("utf-8", "replace").strip()
            _handle_message(shell, text)
            conn.deleteLater()

        conn.readyRead.connect(_read)
        conn.disconnected.connect(_finish)

    server.newConnection.connect(_on_new_connection)
    return server


def _handle_message(shell: Shell, text: str) -> None:
    shell.show_window()
    if not text or text == "__wake__":
        return
    prefix = constants.URI_SCHEME.lower() + "://"
    for token in text.split():
        token = token.strip().strip('"')
        if token.lower().startswith(prefix):
            shell.handle_deeplink(token)


# ────────────────────────── 可选子系统 ──────────────────────────


def _start_cursors(shell: Shell) -> None:
    try:
        from app.cursors import CursorManager
    except Exception as exc:  # noqa: BLE001
        _log.warning("鼠标指针模块不可用：%s", exc)
        return
    try:
        cfg = config_mod.current()
        manager = CursorManager()
        manager.install()
        manager.set_variant(str(cfg.cursor_variant))
        manager.set_enabled(bool(cfg.cursor_enabled))
        shell.cursor_manager = manager
        _log.info("已启用自定义鼠标指针（%s）", cfg.cursor_variant)
    except Exception as exc:  # noqa: BLE001
        _log.warning("鼠标指针启用失败：%s", exc)


def _start_tray(app: QApplication, shell: Shell) -> None:
    try:
        from app.tray import TrayIcon
    except Exception as exc:  # noqa: BLE001
        _log.warning("托盘模块不可用：%s", exc)
        return
    try:
        tray = TrayIcon(app, shell)
        tray.show()
        shell.tray = tray
    except Exception as exc:  # noqa: BLE001
        _log.warning("托盘创建失败：%s", exc)


def _start_pet(shell: Shell) -> None:
    try:
        from app.live2d.pet import PetController
    except Exception as exc:  # noqa: BLE001
        _log.warning("Live2D 桌宠模块不可用：%s", exc)
        return
    try:
        controller = PetController(shell)
        shell.pet_controller = controller
        if config_mod.current().get("pet.enabled", True):
            controller.start()
    except Exception as exc:  # noqa: BLE001
        _log.warning("桌宠启动失败：%s", exc)


# ────────────────────────── 入口 ──────────────────────────


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv if argv is None else argv)
    debug = "--debug" in argv
    minimized = any(a in ("--minimized", "--tray", "/minimized") for a in argv)
    urls = deeplink.extract_urls(argv)

    app = _setup_app(argv, debug)
    _log.info("%s 客户端启动 v%s", constants.APP_NAME, constants.APP_VERSION)

    if _forward_to_existing(urls, minimized=minimized):
        return 0

    cfg = config_mod.current()
    theme.apply(app, cfg.theme)

    shell = Shell()
    cfg.add_listener(shell.on_config_changed)

    server = _start_single_instance_server(shell)
    shell._single_instance_server = server  # 保持引用，避免被回收

    _start_cursors(shell)
    _start_tray(app, shell)
    _start_pet(shell)

    for url in urls:
        shell.handle_deeplink(url)

    if minimized:
        shell.hide()
    else:
        shell.show()

    code = app.exec()
    try:
        shell.save_geometry()
        shell.world_panel.stop()
        if shell.pet_controller is not None:
            shell.pet_controller.stop()
    except Exception:
        pass
    # 等后台请求收尾，避免工作线程在解释器销毁阶段访问已释放对象
    api_mod.wait_for_pending(3000)
    try:
        cfg.save()
    except Exception:
        pass
    _log.info("客户端退出（code=%s）", code)
    return code


if __name__ == "__main__":
    sys.exit(main())
