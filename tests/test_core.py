# -*- coding: utf-8 -*-
"""核心层用例：常量 / 加密 / 路径 / 配置 / 年制 / 主题 / 工具。"""

from __future__ import annotations

import json
import os
import tempfile

from app import constants, crypto, paths, theme, util, yearmode
from app import config as config_mod


# ────────────────────── 常量 ──────────────────────


def test_base_url_obfuscated_and_correct():
    assert constants.BASE_URL == "https://www.yjlt.top"
    assert constants.UPDATE_EXE_URL.endswith("/api/app/windows/forum.exe")
    assert constants.absolute("/avatar/1.webp") == constants.BASE_URL + "/avatar/1.webp"
    assert constants.absolute("https://x.com/a") == "https://x.com/a"
    assert constants.api("/api/posts") == constants.BASE_URL + "/api/posts"


def test_category_labels_exact():
    assert [(k, constants.category_label(k)) for k in constants.CATEGORY_ORDER] == [
        ("general", "综合"), ("talk", "闲聊"), ("question", "求助"),
        ("share", "分享"), ("creative", "创作"),
    ]
    labels = set(constants.CATEGORY_LABELS.values())
    for removed in ("叶羽", "创意"):
        assert removed not in labels


def test_resource_paths_exist():
    assert constants.RES_ICON.is_file()
    assert constants.RES_LOGO.is_file()
    assert constants.RES_FAVICON.is_file()
    assert constants.RES_CURSOR_MANIFEST.is_file()
    assert constants.RES_WIKI_OFFICIAL.is_file()
    assert constants.RES_WIKI_PERSONAL.is_file()
    assert constants.RES_MOUSE_BANNER.is_file()
    assert constants.RES_MOUSE_CREDITS.is_file()
    for item in constants.DEFAULT_AVATAR_POOL:
        assert item.is_file(), item


# ────────────────────── 加密 ──────────────────────


def test_obfuscation_round_trip():
    text = "https://example.com/路径?x=1"
    assert crypto.reveal(crypto.hide(text)) == text


def test_seal_unseal_round_trip():
    payload = "token---abc.def---1700000000|中文".encode("utf-8")
    blob = crypto.seal(payload)
    assert blob.startswith(b"CRF1")
    assert crypto.unseal(blob) == payload
    assert crypto.seal(payload) != crypto.seal(payload)  # nonce 随机


def test_seal_tamper_detected():
    blob = bytearray(crypto.seal(b"hello"))
    blob[-1] ^= 0xFF
    try:
        crypto.unseal(bytes(blob))
    except ValueError:
        return
    raise AssertionError("篡改应导致校验失败")


def test_unseal_rejects_garbage():
    for bad in (b"", b"notcipher", b"CRF1short"):
        try:
            crypto.unseal(bad)
        except ValueError:
            continue
        raise AssertionError("垃圾输入应当报 ValueError")


# ────────────────────── 路径 ──────────────────────


def test_data_dirs_created():
    root = paths.ensure_dirs()
    assert str(root) == os.environ["CRFORUM_DATA_DIR"]
    for folder in paths.all_dirs():
        assert folder.is_dir(), folder
    assert str(paths.config_file()).endswith("config.json")
    assert str(paths.account_file()).endswith("account.bin")


# ────────────────────── 配置 ──────────────────────


def test_config_defaults_and_roundtrip():
    path = os.path.join(tempfile.mkdtemp(), "config.json")
    cfg = config_mod.Config(path)
    assert cfg.get("theme") == "auto"
    assert cfg.get("year_mode") == "wuxian"
    assert cfg.get("pet.enabled") is True
    assert cfg.get("pet.anchor") == "bottom-right"
    assert cfg.get("world.width") == constants.WORLD_WIDTH_DEFAULT
    assert cfg.get("window.w") == 1180

    cfg.set("theme", "night")
    cfg.set("pet.scale", 1.25)
    cfg.set("world.width", 400)
    again = config_mod.Config(path)
    assert again.get("theme") == "night"
    assert abs(float(again.get("pet.scale")) - 1.25) < 1e-6
    assert again.get("world.width") == 400
    # 新增的未知键不会把缺省值顶掉
    raw = json.loads(open(path, encoding="utf-8").read())
    assert raw["pet"]["passthrough"] is False


def test_config_listener():
    path = os.path.join(tempfile.mkdtemp(), "config.json")
    cfg = config_mod.Config(path)
    seen: list[str] = []
    cfg.add_listener(seen.append)
    cfg.set("theme", "day")
    cfg.update({"theme": "night", "nav_mode": "top"})
    assert "theme" in seen and "nav_mode" in seen
    assert seen.count("theme") >= 1


def test_config_deep_merge_keeps_new_keys():
    path = os.path.join(tempfile.mkdtemp(), "config.json")
    with open(path, "w", encoding="utf-8") as fh:
        json.dump({"theme": "day", "pet": {"scale": 2.0}}, fh)
    cfg = config_mod.Config(path)
    assert cfg.get("theme") == "day"
    assert cfg.get("pet.scale") == 2.0
    assert cfg.get("pet.fps") == 60          # 内置缺省
    assert cfg.get("world.width") == constants.WORLD_WIDTH_DEFAULT


# ────────────────────── 年制 / 时间 ──────────────────────


def test_wuxian_conversion():
    assert yearmode.wuxian_year(1604) == 0
    assert yearmode.wuxian_year(1947) == 343
    assert yearmode.wuxian_year(1927) == 323
    assert yearmode.wuxian_year(1603) is None
    assert yearmode.wuxian_to_ce(343) == "1947"
    assert yearmode.wuxian_to_ce(-323) == "1281"
    assert yearmode.wuxian_to_ce("x") == ""
    assert yearmode.wuxian_year_label(1927) == "无限323年"
    assert yearmode.wuxian_year_label(1590) == "无限前14年"


def test_year_text_by_mode():
    assert yearmode.year_text(1947, "wuxian") == "无限343"
    assert yearmode.year_text(1947, "ce") == "1947"
    assert yearmode.year_text(1500, "wuxian") == "无限前104"


def test_parse_time_treats_naive_as_utc():
    dt = yearmode.parse_time("2026-09-25 15:17:13.359183")
    assert dt is not None
    assert dt.year == 2026 and dt.month == 9 and dt.day == 25
    assert dt.hour == 15 and dt.minute == 17 and dt.second == 13
    assert dt.utcoffset().total_seconds() == 0


def test_parse_time_with_explicit_timezone():
    dt = yearmode.parse_time("2026-09-25T15:17:13+08:00")
    assert dt is not None and dt.utcoffset().total_seconds() == 8 * 3600


def test_parse_time_rejects_garbage():
    assert yearmode.parse_time("") is None
    assert yearmode.parse_time("刚刚") is None


def test_fmt_time_relative():
    from datetime import datetime, timedelta, timezone
    now = datetime.now(timezone.utc)
    recent = (now - timedelta(seconds=30)).strftime("%Y-%m-%d %H:%M:%S")
    minutes = (now - timedelta(minutes=5)).strftime("%Y-%m-%d %H:%M:%S")
    hours = (now - timedelta(hours=3)).strftime("%Y-%m-%d %H:%M:%S")
    assert yearmode.fmt_time(recent) == "刚刚"
    assert yearmode.fmt_time(minutes) == "5 分钟前"
    assert yearmode.fmt_time(hours) == "3 小时前"
    older = (now - timedelta(days=3)).strftime("%Y-%m-%d %H:%M:%S")
    assert "-" in yearmode.fmt_time(older)


def test_birthday_helpers():
    assert yearmode.to_date_value(20120615) == "2012-06-15"
    assert yearmode.to_date_value(0) == ""
    assert yearmode.to_date_value("bad") == ""
    assert yearmode.from_date_value("2012-06-15") == 20120615
    assert yearmode.from_date_value("2012/6/5") == 20120605
    assert yearmode.from_date_value("") == 0
    assert yearmode.fmt_birthday(20120615, "wuxian") == "无限408-06-15"
    assert yearmode.fmt_birthday(20120615, "ce") == "2012-06-15"


def test_strip_markdown():
    text = "## 标题\n\n**粗体** 与 `代码`，还有 [链接](https://a.b) 与 ![图](x.png)\n> 引用\n- 列表"
    plain = yearmode.strip_markdown(text)
    for token in ("##", "**", "`", "](", "!", ">", "- "):
        assert token not in plain, (token, plain)
    assert "标题" in plain and "粗体" in plain and "链接" in plain


# ────────────────────── 主题 ──────────────────────


def test_theme_palettes_and_qss():
    assert theme.resolve_mode("day") == "day"
    assert theme.resolve_mode("night") == "night"
    assert theme.resolve_mode("auto") in ("day", "night")
    day = theme.qss("day")
    night = theme.qss("night")
    assert len(day) > 2000 and len(night) > 2000
    assert "#6A8C89" in day and "#84A8B9" in night
    # 模板占位符必须全部被替换掉（包括 radius 这种二次替换的）
    for placeholder in ("{text_primary}", "{bg_card}", "{radius}", "{primary}"):
        assert placeholder not in day, placeholder
        assert placeholder not in night, placeholder
    assert "#E8EEED" in theme.document_css("night")


def test_theme_palette_keys_consistent():
    day = theme.palette("day")
    night = theme.palette("night")
    assert set(day) == set(night)
    for key in ("text_primary", "bg_body", "bg_card", "primary", "border"):
        assert day[key].startswith("#") and night[key].startswith("#")


# ────────────────────── 工具 ──────────────────────


def test_is_external_link():
    assert util.is_external_link("https://www.bilibili.com/x") is True
    assert util.is_external_link("http://example.com") is True
    assert util.is_external_link("https://www.yjlt.top/post/1") is False
    assert util.is_external_link("https://yjlt.top/x") is False
    assert util.is_external_link("/GoTo?to=x") is False
    assert util.is_external_link("#anchor") is False
    assert util.is_external_link("") is False


def test_human_size():
    assert util.human_size(0) == "0 B"
    assert util.human_size(512) == "512 B"
    assert util.human_size(1024) == "1.0 KB"
    assert util.human_size(25190823) == "24.0 MB"


def test_html_escape_and_plain():
    assert util.html_escape('<a x="1">') == "&lt;a x=&quot;1&quot;&gt;"
    assert util.plain("<p>a<br>b</p>") == "ab"


def test_safe_filename():
    assert "/" not in util.safe_filename("a/b:c*d?e")
    assert util.safe_filename("") == "file"
    assert util.safe_filename("...") == "file"


# ────────────────────── 路径（按版本隔离的更新目录） ──────────────────────


def test_update_dir_is_per_version():
    assert paths.update_dir("").name == "update"
    assert paths.update_dir("1.3.2").name == "1.3.2"
    assert paths.update_dir("1.3.2") == paths.data_dir() / "update" / "1.3.2"
    assert paths.update_dir("1.3.2") != paths.update_dir("1.3.1")


def test_safe_component_blocks_traversal():
    assert paths.safe_component("1.3.2") == "1.3.2"
    assert paths.safe_component("a/b") == "b"
    assert paths.safe_component("..\\..\\etc") == "etc"
    assert ".." not in paths.safe_component("../../etc/passwd")
    assert paths.safe_component("...") == "latest"
    assert paths.safe_component("") == "latest"
    assert paths.safe_component("", "") == ""
    # 版本号里的非法字符会被压成下划线，且不会带出分隔符
    assert "/" not in paths.safe_component("1.3.2/../../x")
    assert paths.update_dir("../../x").name == "x"
