"""验证前端时间差自动补齐本地与 UTC 偏移：
   1. fmtTime 不得再硬编码 +08:00 时区。
   2. 后端下发的无时区时间字符串（"YYYY-MM-DD HH:MM:SS"）必须按 UTC 解析，
      由 Date 对象自动换算成浏览器本地时区显示（即 getTimezoneOffset 生效）。
   3. 已带时区后缀（+00:00 / +08:00 / Z）的时间字符串必须按原样解析，不做二次换算。
"""
import os
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

AFTERBODY = os.path.join(PROJECT_ROOT, "static", "js", "AfterBody.js")


def _read(path):
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def test_no_hardcoded_plus0800():
    """fmtTime 中不允许再出现写死的 +08:00（时间差应交给 getTimezoneOffset 自动补齐）。"""
    js = _read(AFTERBODY)
    m = js[js.find("function fmtTime"): js.find("function el(")]
    assert "+08:00" not in m, "fmtTime 仍硬编码 +08:00，需改为按本地时区自动补齐"


def test_naive_time_parsed_as_utc():
    """无时区后缀的时间字符串必须追加 Z（UTC）再解析，实现本地与 UTC 自动补齐。"""
    js = _read(AFTERBODY)
    parse_fn = js[js.find("function parseTime"): js.find("function fmtTime")]
    assert "iso + 'Z'" in parse_fn or "iso+'Z'" in parse_fn, (
        "parseTime 未把无时区字符串按 UTC（追加 Z）解析，无法自动补齐本地时区差"
    )


def test_tz_aware_time_parsed_as_is():
    """已带时区后缀的字符串应直接交给 Date 解析，禁止二次拼接 Z。"""
    js = _read(AFTERBODY)
    parse_fn = js[js.find("function parseTime"): js.find("function fmtTime")]
    assert "[zZ]$" in parse_fn, "parseTime 缺少 Z/z 结尾（UTC 后缀）识别"
    assert "[+-]\\d{2}" in parse_fn, "parseTime 缺少 +HH:MM 时区偏移识别"


def test_timezone_offset_in_fmt_time_path():
    """Date 对象必须在 parseTime 中构建，确保本地时区换算（getHours/getFullYear）基于真实时刻。"""
    js = _read(AFTERBODY)
    fmt_body = js[js.find("function fmtTime"): js.find("function el(")]
    assert "parseTime(t)" in fmt_body, "fmtTime 未通过 parseTime 解析时间"


if __name__ == "__main__":
    tests = [
        ("test_no_hardcoded_plus0800", test_no_hardcoded_plus0800),
        ("test_naive_time_parsed_as_utc", test_naive_time_parsed_as_utc),
        ("test_tz_aware_time_parsed_as_is", test_tz_aware_time_parsed_as_is),
        ("test_timezone_offset_in_fmt_time_path", test_timezone_offset_in_fmt_time_path),
    ]
    passed = 0
    failed = 0
    for name, fn in tests:
        try:
            fn()
            print(f"PASS  {name}")
            passed += 1
        except AssertionError as e:
            print(f"FAIL  {name}: {e}")
            failed += 1
        except Exception as e:
            print(f"ERROR {name}: {type(e).__name__}: {e}")
            failed += 1
    print(f"\n{passed} passed, {failed} failed")
    sys.exit(0 if failed == 0 else 1)
