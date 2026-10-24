"""验证 main.py 顶部有防御性 sys.path 注入，避免 uv package=false 时找不到 api/db/tool 包。"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def test_main_py_has_sys_path_injection():
    """main.py 顶部必须执行 sys.path.insert(0, 项目根)，且在 from app import 之前；项目根须基于 __file__。"""
    main_src = (ROOT / "main.py").read_text(encoding="utf-8")

    # 按行定位：insert 调用行号 < from app import 行号，且源码里项目根计算基于 __file__
    app_import_line = None
    insert_line = None
    for i, line in enumerate(main_src.splitlines(), 1):
        if re.search(r"^\s*from app import", line) and app_import_line is None:
            app_import_line = i
        if "sys.path.insert(0" in line and insert_line is None:
            insert_line = i

    assert insert_line is not None, "main.py 未找到 sys.path.insert(0, ...) 调用"
    assert app_import_line is not None, "main.py 未找到 from app import create_app"
    assert insert_line < app_import_line, (
        "sys.path.insert 必须出现在 `from app import create_app` 之前，"
        "否则 uv package=false 下找不到 api/db/tool 包。"
    )

    # 项目根计算必须基于 __file__（而不是 CWD），保证从任何目录启动都正确
    assert "__file__" in main_src, "main.py 项目根计算未基于 __file__"

    print("PASS: main.py 顶部有 sys.path.insert(0, 基于 __file__ 的项目根) 且在 app 导入之前")


if __name__ == "__main__":
    test_main_py_has_sys_path_injection()
    print("ALL_PASSED")
