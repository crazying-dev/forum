# -*- coding: utf-8 -*-
"""状态码日志（2xx / 4xx / 5xx）+ 查询接口 GET /api/status-log 的回归测试。"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def _client():
    """最小 app：只注册 status_bp（不触发 app.py 的 DB / 鉴权中间件）。"""
    from flask import Flask
    from api.status import status_bp

    app = Flask(__name__)
    app.config["JSON_AS_ASCII"] = False
    app.register_blueprint(status_bp, url_prefix="/api")
    return app.test_client()


def _use_tmp_log(tmp_path, monkeypatch, max_entries=None):
    """把日志文件重定向到临时目录，避免污染仓库。"""
    import config
    import api.status as st

    monkeypatch.setattr(config, "STATUS_LOG_PATH", str(tmp_path / "status.log"))
    if max_entries is not None:
        monkeypatch.setattr(config, "STATUS_LOG_MAX", max_entries)
    return st


def test_status_class_mapping():
    from api.status import status_class

    assert status_class(200) == "2xx"
    assert status_class(204) == "2xx"
    assert status_class(301) == "3xx"
    assert status_class(404) == "4xx"
    assert status_class(429) == "4xx"
    assert status_class(500) == "5xx"
    assert status_class("200") == "2xx"
    assert status_class(None) == ""
    assert status_class(999) == ""


def test_record_only_tracks_2xx_4xx_5xx(tmp_path, monkeypatch):
    st = _use_tmp_log(tmp_path, monkeypatch)
    st.record(200)
    st.record(404)
    st.record(500)
    st.record(302)  # 3xx 不记录
    st.record(101)  # 1xx 不记录
    entries = st.recent()
    assert [e["status"] for e in entries] == [500, 404, 200], "应为倒序（最新在前）"
    for e in entries:
        assert set(e) == {"time", "status"}, "只记录时间 + 状态码（无 class、无路径）"
        assert "T" in e["time"], "时间应为 ISO 格式"


def test_trim_keeps_latest_n(tmp_path, monkeypatch):
    st = _use_tmp_log(tmp_path, monkeypatch, max_entries=5)
    for _ in range(12):
        st.record(200)
    lines = [ln for ln in (tmp_path / "status.log").read_text(encoding="utf-8").splitlines() if ln.strip()]
    assert len(lines) == 5, "日志文件应裁剪到最近 5 条"
    assert len(st.recent()) == 5


def test_api_returns_recent_entries(tmp_path, monkeypatch):
    st = _use_tmp_log(tmp_path, monkeypatch)
    st.record(200)
    st.record(404)
    rv = _client().get("/api/status-log")
    assert rv.status_code == 200
    data = rv.get_json()
    assert data["success"] is True
    assert data["count"] == 2
    assert data["entries"][0]["status"] == 404
    assert data["entries"][1]["status"] == 200
    # 返回项不包含 class / 路径等额外字段
    assert set(data["entries"][0]) == {"time", "status"}


def test_api_has_no_parameters(tmp_path, monkeypatch):
    """接口不接受任何参数：带查询串也一律返回全部明细。"""
    st = _use_tmp_log(tmp_path, monkeypatch)
    for _ in range(5):
        st.record(200)
    c = _client()
    assert c.get("/api/status-log").get_json()["count"] == 5
    assert c.get("/api/status-log?limit=2").get_json()["count"] == 5
    assert c.get("/api/status-log?foo=bar").get_json()["count"] == 5
    assert "limit" not in c.get("/api/status-log").get_json()


def test_api_empty_without_file(tmp_path, monkeypatch):
    import config

    monkeypatch.setattr(config, "STATUS_LOG_PATH", str(tmp_path / "missing.log"))
    data = _client().get("/api/status-log").get_json()
    assert data["success"] is True
    assert data["entries"] == []
    assert data["count"] == 0


def test_status_log_max_default_is_10000():
    """默认上限 10000 条：config.py 源码默认与 api/status.py 兜底常量必须一致。"""
    import api.status as st

    cfg = (ROOT / "config.py").read_text(encoding="utf-8")
    assert 'os.getenv("STATUS_LOG_MAX", "10000")' in cfg, "config.py 的默认上限应改为 10000"
    assert st._DEFAULT_MAX == 10000, "api/status.py 的兜底常量应为 10000"


def test_max_entries_falls_back_to_default(tmp_path, monkeypatch):
    """config 值非法（0 / 负数）时回退到默认上限 10000，而不是裁到 0 条。"""
    import config
    import api.status as st

    monkeypatch.setattr(config, "STATUS_LOG_MAX", 0)
    assert st._max_entries() == 10000
    monkeypatch.setattr(config, "STATUS_LOG_MAX", -5)
    assert st._max_entries() == 10000


def test_blueprint_and_hook_wired():
    api_init = (ROOT / "api" / "__init__.py").read_text(encoding="utf-8")
    assert "status_bp" in api_init, "api/__init__.py 未注册 status_bp"
    app_py = (ROOT / "app.py").read_text(encoding="utf-8")
    assert "STATUS_LOG" in app_py, "app.py 未接入状态码日志开关"
    assert "record_status_code" in app_py, "app.py 未在 after_request 中记录状态码"
    cfg = (ROOT / "config.py").read_text(encoding="utf-8")
    assert "STATUS_LOG_PATH" in cfg and "STATUS_LOG_MAX" in cfg, "config.py 缺少状态码日志配置"
