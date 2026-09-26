# -*- coding: utf-8 -*-
"""时间与年制：无限年 / 公元年换算、相对时间格式化、Markdown 摘要提取。

口径完全对齐 Web 端（static/js/AfterBody.js）：

* 无限年 = 公元年 − 1604（无限元年 = 公元 1604 年）
* 公元年 < 1604 时显示「无限前xxx」
* 后端时间字符串无时区信息时按 **UTC** 解析，再换算到本地时区显示
"""

from __future__ import annotations

import re
from datetime import datetime, timezone

from . import config, constants

_TZ_RE = re.compile(r"(?:[zZ]|[+-]\d{2}:?\d{2})$")
_TIME_RE = re.compile(r":\d{2}")


# ────────────────────────── 年制 ──────────────────────────


def epoch() -> int:
    return constants.WUXIAN_EPOCH_CE


def get_mode() -> str:
    try:
        mode = str(config.current().get("year_mode", constants.YEAR_MODE_DEFAULT))
    except Exception:
        mode = constants.YEAR_MODE_DEFAULT
    return constants.YEAR_MODE_CE if mode == constants.YEAR_MODE_CE else constants.YEAR_MODE_WUXIAN


def set_mode(mode: str) -> str:
    mode = constants.YEAR_MODE_CE if mode == constants.YEAR_MODE_CE else constants.YEAR_MODE_WUXIAN
    try:
        config.current().set("year_mode", mode)
    except Exception:
        pass
    return mode


def wuxian_year(ce) -> int | None:
    """公元年 → 无限年；公元年 < 1604 时返回 None。"""
    try:
        ce = int(ce)
    except (TypeError, ValueError):
        return None
    if ce < constants.WUXIAN_EPOCH_CE:
        return None
    return ce - constants.WUXIAN_EPOCH_CE


def wuxian_to_ce(wy) -> str:
    """无限年 → 公元年（允许负数，表示无限前）。非法输入返回空串。"""
    try:
        wy = int(wy)
    except (TypeError, ValueError):
        return ""
    return str(wy + constants.WUXIAN_EPOCH_CE)


def wuxian_year_label(ce) -> str | None:
    try:
        ce = int(ce)
    except (TypeError, ValueError):
        return None
    if ce >= constants.WUXIAN_EPOCH_CE:
        return "无限%d年" % (ce - constants.WUXIAN_EPOCH_CE)
    return "无限前%d年" % (constants.WUXIAN_EPOCH_CE - ce)


def year_text(ce, mode: str | None = None) -> str:
    """按当前年制格式化「年」部分（不带“年”字）。"""
    try:
        ce = int(ce)
    except (TypeError, ValueError):
        return ""
    mode = mode or get_mode()
    if mode == constants.YEAR_MODE_CE:
        return str(ce)
    wy = wuxian_year(ce)
    if wy is not None:
        return "无限%d" % wy
    return "无限前%d" % (constants.WUXIAN_EPOCH_CE - ce)


# ────────────────────────── 时间 ──────────────────────────


def parse_time(t) -> datetime | None:
    """把后端时间字符串解析为带时区的 datetime。

    无时区信息时按 UTC 处理（与 Web 端 ``parseTime`` 一致）。
    """
    if t is None:
        return None
    s = str(t).strip()
    if not s:
        return None
    if _TZ_RE.search(s):
        iso = s
    else:
        iso = s.replace(" ", "T")
        if _TIME_RE.search(iso):
            iso = iso + "Z"
    try:
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
    except ValueError:
        dt = None
        for fmt in ("%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S",
                    "%Y-%m-%dT%H:%M:%S.%f", "%Y-%m-%dT%H:%M:%S",
                    "%Y-%m-%d", "%Y/%m/%d %H:%M:%S"):
            try:
                dt = datetime.strptime(s, fmt)
                break
            except ValueError:
                continue
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def fmt_time(t, mode: str | None = None) -> str:
    """相对时间（刚刚 / N 分钟前 / N 小时前），超过 1 天则显示绝对时间。"""
    if not t:
        return ""
    dt = parse_time(t)
    if dt is None:
        return str(t)
    diff = (datetime.now(timezone.utc) - dt).total_seconds()
    if diff < 60:
        return "刚刚"
    if diff < 3600:
        return "%d 分钟前" % int(diff // 60)
    if diff < 86400:
        return "%d 小时前" % int(diff // 3600)
    local = dt.astimezone()
    return "%s-%02d-%02d %02d:%02d" % (
        year_text(local.year, mode), local.month, local.day, local.hour, local.minute)


def fmt_datetime(t, mode: str | None = None) -> str:
    """绝对时间（不做相对化），用于详情页等需要精确时刻的位置。"""
    dt = parse_time(t)
    if dt is None:
        return "" if not t else str(t)
    local = dt.astimezone()
    return "%s-%02d-%02d %02d:%02d" % (
        year_text(local.year, mode), local.month, local.day, local.hour, local.minute)


# ────────────────────────── 生日 ──────────────────────────


def to_date_value(age) -> str:
    """后端生日整数（如 20120615）→ ``YYYY-MM-DD``。"""
    if age in (None, "", 0):
        return ""
    try:
        n = int(age)
    except (TypeError, ValueError):
        return ""
    y, m, d = n // 10000, (n // 100) % 100, n % 100
    if y < 1000 or not (1 <= m <= 12) or not (1 <= d <= 31):
        return ""
    return "%04d-%02d-%02d" % (y, m, d)


def from_date_value(text) -> int:
    """``YYYY-MM-DD`` → 后端生日整数（非法输入返回 0）。"""
    if not text:
        return 0
    m = re.match(r"^(\d{4})[-/](\d{1,2})[-/](\d{1,2})$", str(text).strip())
    if not m:
        return 0
    return int(m.group(1)) * 10000 + int(m.group(2)) * 100 + int(m.group(3))


def fmt_birthday(age, mode: str | None = None) -> str:
    """生日展示（V1 风格：年-月-日，年部分跟随年制）。"""
    text = to_date_value(age)
    if not text:
        return ""
    y, m, d = text.split("-")
    return "%s-%s-%s" % (year_text(int(y), mode), m, d)


# ────────────────────────── 摘要 ──────────────────────────


def strip_markdown(s) -> str:
    """剔除 Markdown 标记 → 纯文本（用于卡片摘要预览）。"""
    if not s:
        return ""
    t = str(s)
    t = re.sub(r"```[\s\S]*?```", " ", t)
    t = re.sub(r"`([^`]*)`", r"\1", t)
    t = re.sub(r"!\[([^\]]*)\]\([^)]*\)", r"\1", t)
    t = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", t)
    t = re.sub(r"^#{1,6}\s+", "", t, flags=re.M)
    t = re.sub(r"(\*\*|__)(.*?)\1", r"\2", t)
    t = re.sub(r"([*_])([^*_]+)\1", r"\2", t)
    t = re.sub(r"^>\s?", "", t, flags=re.M)
    t = re.sub(r"^\s*[-+*]\s+", "", t, flags=re.M)
    t = re.sub(r"^\s*\d+\.\s+", "", t, flags=re.M)
    t = re.sub(r"<[^>]+>", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def short_age(age) -> str:
    """取年龄数字（用于“N 岁”展示）；非法时返回空串。"""
    try:
        n = int(age)
    except (TypeError, ValueError):
        return ""
    if n <= 0:
        return ""
    today = datetime.now()
    y, m, d = n // 10000, (n // 100) % 100, n % 100
    if y < 1000:
        return ""
    years = today.year - y - ((today.month, today.day) < (m, d))
    return str(years) if 0 <= years < 200 else ""
