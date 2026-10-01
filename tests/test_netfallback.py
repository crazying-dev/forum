# -*- coding: utf-8 -*-
"""下载回退链（直连 → DoH → 公共加速 → 服务器反代）与安装脚本修复的离线用例。

不依赖 pytest 夹具：``tests/run_tests.py`` 以无参形式逐个调用用例函数。
"""
from __future__ import annotations

import inspect
import socket
from pathlib import Path

from app import constants, netfallback, paths, updater

GH_URL = ("https://github.com/crazying-dev/forum/releases/download/"
          "Windows-V1.3.4/forum_setup.exe")
SERVER_URL = "https://yjlt.top/api/app/windows/forum.exe"

_PATCHES: list = []


def _patch(obj, name, value) -> None:
    had = hasattr(obj, name)
    old = getattr(obj, name, None)
    _PATCHES.append((obj, name, had, old))
    setattr(obj, name, value)


def _restore_all() -> None:
    while _PATCHES:
        obj, name, had, old = _PATCHES.pop()
        if had:
            setattr(obj, name, old)
        else:
            try:
                delattr(obj, name)
            except AttributeError:
                pass


# ────────────────────── GitHub 域名判定 ──────────────────────


def test_is_github_host_and_url():
    assert netfallback.is_github_host("github.com") is True
    assert netfallback.is_github_host("objects.githubusercontent.com") is True
    assert netfallback.is_github_host("RELEASE-ASSETS.GITHUBUSERCONTENT.COM.") is True
    assert netfallback.is_github_host("yjlt.top") is False
    assert netfallback.is_github_host("evil-github.com") is False
    assert netfallback.is_github_host("") is False
    assert netfallback.is_github_url(GH_URL) is True
    assert netfallback.is_github_url(SERVER_URL) is False
    assert netfallback.is_github_url("") is False


# ────────────────────── 加速 / 反代地址 ──────────────────────


def test_accelerate_prefixes_original_url():
    urls = netfallback.accelerate(GH_URL)
    assert urls, "应至少内置一个公共加速镜像"
    assert len(urls) == len(constants.ACCELERATOR_MIRRORS)
    for item in urls:
        assert item.startswith("https://")
        assert item.endswith(GH_URL)
    assert netfallback.accelerate("") == []


def test_server_mirror_uses_api_path():
    url = netfallback.server_mirror(GH_URL)
    assert "/api/app/mirror/windows/forum_setup.exe" in url
    assert url.startswith(constants.BASE_URL)
    assert netfallback.server_mirror(GH_URL, "forum_setup.exe").endswith("forum_setup.exe")
    assert netfallback.server_mirror("") == ""


def test_download_attempts_order_for_github():
    attempts = netfallback.download_attempts(GH_URL, "forum_setup.exe")
    labels = [item[0] for item in attempts]
    assert labels[0] == "直连"
    assert labels[1] == "DoH 修复"
    assert sum(1 for label in labels if label.startswith("公共加速")) == \
        len(constants.ACCELERATOR_MIRRORS)
    assert labels[-1] == "服务器反代"
    assert attempts[0][1] == GH_URL and attempts[0][2] is False
    assert attempts[1][1] == GH_URL and attempts[1][2] is True
    for _, url, use_doh in attempts[2:]:
        assert use_doh is False
        assert url.startswith("https://")


def test_download_attempts_single_for_non_github():
    assert netfallback.download_attempts(SERVER_URL) == [("直连", SERVER_URL, False)]
    assert netfallback.download_attempts("") == []


# ────────────────────── DoH ──────────────────────


def test_parse_doh_keeps_only_a_records():
    payload = {"Answer": [{"type": 5, "data": "cname"},
                          {"type": 1, "data": "1.2.3.4"},
                          {"type": "1", "data": " 5.6.7.8 "}]}
    assert netfallback._parse_doh(payload) == ["1.2.3.4", "5.6.7.8"]
    assert netfallback._parse_doh(None) == []
    assert netfallback._parse_doh({}) == []
    assert netfallback._parse_doh({"Answer": "nope"}) == []


def test_resolve_skips_failing_doh_endpoint():
    calls: list = []

    class _Resp:
        status_code = 200

        def json(self):
            return {"Answer": [{"type": 1, "data": "9.9.9.9"}]}

        def close(self):
            pass

    def fake_get(url, **kwargs):
        calls.append(url)
        if url == constants.DOH_ENDPOINTS[0]:
            raise RuntimeError("dns down")
        return _Resp()

    netfallback.clear_cache()
    _patch(netfallback.requests, "get", fake_get)
    try:
        ips = netfallback.resolve("github.com")
    finally:
        _restore_all()
        netfallback.clear_cache()
    assert ips == ["9.9.9.9"]
    assert calls == list(constants.DOH_ENDPOINTS[:2])


def test_resolve_returns_empty_when_all_doh_fail():
    def fake_get(url, **kwargs):
        raise RuntimeError("no network")

    netfallback.clear_cache()
    _patch(netfallback.requests, "get", fake_get)
    try:
        assert netfallback.resolve("github.com") == []
    finally:
        _restore_all()
        netfallback.clear_cache()


# ────────────────────── socket 解析接管 ──────────────────────


def test_getaddrinfo_patch_only_hijacks_github():
    seen: list = []
    real = netfallback._real_getaddrinfo

    def fake_resolve(host):
        seen.append(host)
        return ["10.0.0.1"]

    _patch(netfallback, "resolve", fake_resolve)
    try:
        assert netfallback.patched() is False
        with netfallback.doh_dns():
            assert netfallback.patched() is True
            out = socket.getaddrinfo("github.com", 443)
            assert seen == ["github.com"]
            assert out and "10.0.0.1" in str(out[0][4][0])
            seen.clear()
            try:
                socket.getaddrinfo("localhost", 80)
            except Exception:  # noqa: BLE001
                pass
            assert seen == [], "非 GitHub 域名不应走 DoH"
        assert netfallback.patched() is False
        assert socket.getaddrinfo is real
    finally:
        _restore_all()


def test_doh_patch_is_reentrant():
    with netfallback.doh_dns():
        with netfallback.doh_dns():
            assert netfallback.patched() is True
        assert netfallback.patched() is True
    assert netfallback.patched() is False


# ────────────────────── 多级下载 ──────────────────────


def _fake_download_to(results):
    """results: ``[(ok, error), ...]``，按调用顺序依次返回。"""
    state = {"i": 0, "calls": []}

    def fake(url, dest, **kwargs):
        state["calls"].append((url, kwargs.get("resume")))
        index = min(state["i"], len(results) - 1)
        state["i"] += 1
        return results[index]

    return fake, state


def test_download_with_fallback_escalates_until_success():
    fake, state = _fake_download_to([(False, "连接超时"), (False, "连接超时"), (True, "")])
    stages: list = []
    attempts = [("直连", "u1", False), ("DoH 修复", "u2", True), ("服务器反代", "u3", False)]
    _patch(updater, "download_to", fake)
    _patch(updater, "_remove_part", lambda dest: None)
    try:
        ok, error = updater.download_with_fallback(attempts, "dest", on_stage=stages.append)
    finally:
        _restore_all()
    assert ok is True and error == ""
    assert stages == ["直连", "DoH 修复", "服务器反代"]
    # 只有第一次允许续传，换源必须重下
    assert [call[1] for call in state["calls"]] == [True, False, False]


def test_download_with_fallback_returns_last_error():
    fake, state = _fake_download_to([(False, "第一级失败"), (False, "最后一级失败")])
    _patch(updater, "download_to", fake)
    _patch(updater, "_remove_part", lambda dest: None)
    try:
        ok, error = updater.download_with_fallback(
            [("直连", "u1", False), ("服务器反代", "u2", False)], "dest")
    finally:
        _restore_all()
    assert ok is False
    assert error == "最后一级失败"
    assert len(state["calls"]) == 2


def test_download_with_fallback_without_sources():
    ok, error = updater.download_with_fallback([], "dest")
    assert ok is False and error


def test_download_update_wires_fallback_chain():
    source = inspect.getsource(updater.download_update)
    assert "netfallback.download_attempts" in source
    assert "download_with_fallback" in source
    assert "on_stage" in source


def test_remove_part_deletes_part_file():
    target = paths.update_dir("9.9.9") / "forum_setup.exe"
    target.parent.mkdir(parents=True, exist_ok=True)
    part = Path(str(target) + ".part")
    part.write_bytes(b"stale")
    try:
        updater._remove_part(target)
        assert part.exists() is False
    finally:
        try:
            part.unlink()
        except OSError:
            pass


# ────────────────────── 安装脚本（回归） ──────────────────────


def test_write_script_never_produces_double_cr():
    """回归：脚本必须先拼 CRLF 再以 newline="" 原样落盘，绝不得出现 \\r\\r\\n。"""
    target = paths.update_dir("9.9.9") / "apply_update.cmd"
    try:
        updater._write_script(
            target, updater._script_text(Path("C:/u/a.exe"), Path("C:/app/forum.exe")))
        data = target.read_bytes()
        assert b"\r\r\n" not in data, "出现 \\r\\r\\n，cmd 会解析失败"
        assert b"\r\n" in data
        assert b"\n" not in data.replace(b"\r\n", b""), "存在裸 LF"
    finally:
        try:
            target.unlink()
        except OSError:
            pass


def test_scripts_avoid_timeout_and_use_ping():
    """无控制台（GUI 拉起的 cmd）里 timeout 不可用，改用 ping 做延时。"""
    legacy = updater._script_text(Path(r"C:\u\a.exe"), Path(r"C:\app\forum.exe"))
    assert "ping -n 2 127.0.0.1" in legacy
    assert "timeout /t" not in legacy
    # 热替换脚本的原有行为不能回退
    for token in ("move /y", "tasklist", "for /L %%i", 'start "" "%DST%"'):
        assert token in legacy, "热替换脚本缺少 %s" % token


def test_spawn_script_redirects_standard_streams():
    source = inspect.getsource(updater._spawn_script)
    assert "DETACHED_PROCESS" in source
    assert "DEVNULL" in source


# ───────────── 安装包直启（CREATE_NO_WINDOW + atexit） ─────────────


class _FakeAtexit:
    """替代 atexit：只记录回调，绝不真的注册。

    否则 pytest / run_tests 自己退出时会去 Popen 测试用的假 exe。
    """

    def __init__(self) -> None:
        self.handlers: list = []

    def register(self, fn, *args, **kwargs):
        self.handlers.append(fn)
        return fn


def test_spawn_installer_uses_create_no_window():
    """安装包必须用 CREATE_NO_WINDOW 直接唤起，不能再经 cmd / .cmd 中转。"""
    source = inspect.getsource(updater._spawn_installer)
    assert "CREATE_NO_WINDOW" in source
    assert "shell=False" in source
    assert '"cmd"' not in source and "'cmd'" not in source

    recorded: dict = {}
    _patch(updater.subprocess, "Popen",
           lambda argv, **kw: recorded.update(argv=argv, kw=kw))
    try:
        updater._spawn_installer(Path(r"C:\u\1.3.7\forum_setup.exe"))
    finally:
        _restore_all()
    assert recorded["argv"][0] == r"C:\u\1.3.7\forum_setup.exe"
    assert list(recorded["argv"][1:]) == list(updater.INSTALLER_ARGS)
    assert recorded["kw"].get("shell") is False
    assert recorded["kw"].get("creationflags") == getattr(
        updater.subprocess, "CREATE_NO_WINDOW", 0)


def test_schedule_install_on_exit_registers_hook():
    target = paths.update_dir("9.9.7") / "forum_setup.exe"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(b"x")
    fake = _FakeAtexit()
    spawned: list = []
    _patch(updater, "atexit", fake)
    _patch(updater, "_EXIT_INSTALLER", None)
    _patch(updater, "_EXIT_HOOK_REGISTERED", False)
    _patch(updater, "_spawn_installer", lambda path: spawned.append(path))
    try:
        assert updater.schedule_install_on_exit(target) is True
        assert fake.handlers and fake.handlers[0] is updater._run_exit_installer
        assert updater._EXIT_INSTALLER == target
        # 重复登记不重复注册钩子，但会刷新目标
        assert updater.schedule_install_on_exit(target) is True
        assert len(fake.handlers) == 1
        # 退出回调：唤起一次并清空登记
        updater._run_exit_installer()
        assert spawned == [target]
        assert updater._EXIT_INSTALLER is None
        # 再调一次不会重复唤起
        updater._run_exit_installer()
        assert spawned == [target]
        # 安装包不存在时不登记
        assert updater.schedule_install_on_exit(target.parent / "missing.exe") is False
    finally:
        _restore_all()
        try:
            target.unlink()
        except OSError:
            pass


def test_launch_installer_installer_branch_exits_with_zero():
    """「立即安装」：登记退出钩子 → 退出事件循环 → sys.exit(0)。"""
    target = paths.update_dir("9.9.6") / "forum_setup.exe"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(b"x")
    fake = _FakeAtexit()
    quit_called: list = []
    _patch(updater, "atexit", fake)
    _patch(updater, "_EXIT_INSTALLER", None)
    _patch(updater, "_EXIT_HOOK_REGISTERED", False)
    _patch(updater, "_quit_app", lambda: quit_called.append(True))
    _patch(updater.sys, "frozen", True)
    code = "not-raised"
    try:
        try:
            updater.launch_installer(str(target))
        except SystemExit as exc:
            code = exc.code
    finally:
        _restore_all()
        try:
            target.unlink()
        except OSError:
            pass
    assert code == 0
    assert quit_called == [True]
    assert len(fake.handlers) == 1


def test_launch_installer_rejects_dev_mode():
    ok, message = updater.launch_installer("definitely-missing.exe")
    assert ok is False
    assert message
