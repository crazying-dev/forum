# -*- coding: utf-8 -*-
"""测试运行器（不依赖 pytest）。

用法：

    python tests/run_tests.py              # 只跑离线用例
    python tests/run_tests.py --online     # 额外跑需要联网的用例
    python tests/run_tests.py --filter net # 只跑文件名含 net 的用例

行为：

1. 把 ``CRFORUM_DATA_DIR`` 指向临时目录，避免污染真实的 ``~/.Cr/forum``
2. 把工程根目录与 ``tests/`` 加入 ``sys.path``
3. 以模块名 ``t_<文件名>`` 逐个加载 ``tests/test_*.py``
4. 执行模块中所有 ``test_`` 开头的可调用对象，收集失败与回溯
5. 打印 ``PASSED n / FAILED n``，有失败则退出码 1
"""

from __future__ import annotations

import argparse
import importlib.util
import os
import sys
import tempfile
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

# 必须持有引用：QApplication 被 GC 后 Qt 会回到“无 GUI 应用”状态，
# 之后再建 QPixmap/QCursor 会直接 abort。
_APP = None

for path in (ROOT, HERE):
    if path not in sys.path:
        sys.path.insert(0, path)


def _setup_environment(online: bool) -> str:
    global _APP
    data_dir = os.path.join(tempfile.gettempdir(), "crforum_tests")
    os.makedirs(data_dir, exist_ok=True)
    os.environ["CRFORUM_DATA_DIR"] = data_dir
    os.environ["CRFORUM_ONLINE"] = "1" if online else "0"
    # 集中创建一个 QApplication：QPixmap / QCursor 构造函数要求
    # 先有 QGuiApplication，否则 Qt 会直接 abort（且不会刷新 stdout）。
    try:
        from PyQt6.QtWidgets import QApplication
        if QApplication.instance() is None:
            _APP = QApplication([])
        else:
            _APP = QApplication.instance()
    except Exception as exc:  # noqa: BLE001
        print("（无法创建 QApplication，依赖 Qt 的用例会失败：%s）" % exc)
    return data_dir


def _wait_for_pending() -> None:
    """退出前等后台请求收尾，避免任务信号在解释器销毁阶段被回收。"""
    try:
        from app import api as api_mod
        api_mod.wait_for_pending(3000)
    except Exception:
        pass


def _load_module(path: str):
    name = "t_" + os.path.splitext(os.path.basename(path))[0]
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError("无法加载 %s" % path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _collect_cases(module) -> list:
    cases = []
    for name in sorted(dir(module)):
        if not name.startswith("test_"):
            continue
        obj = getattr(module, name)
        if callable(obj) and getattr(obj, "__module__", "") == module.__name__:
            cases.append((name, obj))
    return cases


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="妖精论坛客户端测试运行器")
    parser.add_argument("--online", action="store_true",
                        help="额外运行需要联网的用例（默认跳过）")
    parser.add_argument("--filter", default="", help="仅运行文件名包含该子串的用例文件")
    parser.add_argument("--verbose", action="store_true", help="打印每个用例的名称")
    args = parser.parse_args(argv)

    data_dir = _setup_environment(args.online)
    print("数据目录 :", data_dir)
    print("联网用例 :", "开启" if args.online else "跳过（--online 开启）")
    print()

    files = sorted(
        os.path.join(HERE, name)
        for name in os.listdir(HERE)
        if name.startswith("test_") and name.endswith(".py")
    )
    if args.filter:
        files = [f for f in files if args.filter in os.path.basename(f)]
    if not files:
        print("没有找到用例文件")
        return 0

    passed = 0
    failed = 0
    failures: list[str] = []

    for path in files:
        label = os.path.basename(path)
        try:
            module = _load_module(path)
        except Exception:  # noqa: BLE001
            failed += 1
            failures.append("%s 导入失败:\n%s" % (label, traceback.format_exc()))
            print("== %-28s 导入失败" % label)
            continue
        cases = _collect_cases(module)
        if not cases:
            print("== %-28s （无用例）" % label)
            continue
        file_ok = 0
        file_fail = 0
        for name, fn in cases:
            try:
                fn()
            except Exception:  # noqa: BLE001
                file_fail += 1
                failures.append("%s::%s\n%s" % (label, name, traceback.format_exc()))
                print("   [FAIL] %s" % name)
            else:
                file_ok += 1
                if args.verbose:
                    print("   [ok]   %s" % name)
        passed += file_ok
        failed += file_fail
        flag = "OK " if not file_fail else "FAIL"
        print("== %-28s %s  %d passed, %d failed" % (label, flag, file_ok, file_fail))

    print()
    if failures:
        print("=" * 68)
        for item in failures:
            print(item)
            print("-" * 68)
    print("PASSED %d / FAILED %d" % (passed, failed))
    _wait_for_pending()
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
