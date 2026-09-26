# -*- coding: utf-8 -*-
"""HTTPS 根证书用例：内置证书可用性 / 候选优先级 / 环境变量注入 / ssl 加载。

对应修复：打包后世界频道报“安全连接失败”（certifi 证书包陈旧）。
"""

from __future__ import annotations

import os
import ssl
import tempfile

from app import constants
from app import tls as tls_mod

ONLINE = os.environ.get("CRFORUM_ONLINE") == "1"


# ────────────────────── 内置证书 ──────────────────────


def test_bundled_ca_exists_and_is_sane():
    path = constants.RES_CA_BUNDLE
    assert path.is_file(), path
    assert tls_mod._is_sane(path) is True
    assert path.stat().st_size > tls_mod.MIN_BUNDLE_BYTES


def test_candidates_prefer_bundled():
    items = tls_mod.candidates()
    assert items, items
    assert items[0] == str(constants.RES_CA_BUNDLE)


def test_is_sane_rejects_missing_and_tiny():
    assert tls_mod._is_sane("") is False
    assert tls_mod._is_sane(None) is False
    missing = os.path.join(tempfile.mkdtemp(), "nope.pem")
    assert tls_mod._is_sane(missing) is False
    tiny = os.path.join(tempfile.mkdtemp(), "tiny.pem")
    with open(tiny, "w", encoding="utf-8") as fh:
        fh.write("not a bundle")
    assert tls_mod._is_sane(tiny) is False


# ────────────────────── 解析 / 注入 ──────────────────────


def test_bundle_path_is_usable():
    path = tls_mod.bundle_path()
    assert path, "应当能找到一份可用的根证书"
    assert os.path.isfile(path)
    assert os.path.getsize(path) >= tls_mod.MIN_BUNDLE_BYTES


def test_install_sets_environment_and_verify_target():
    path = tls_mod.install()
    assert path, "install() 应返回证书路径"
    assert os.environ.get("REQUESTS_CA_BUNDLE") == path
    assert os.environ.get("SSL_CERT_FILE") == path
    assert tls_mod.verify_target() == path
    # 幂等：重复调用不报错，结果一致
    assert tls_mod.install() == path


def test_bundle_loadable_by_ssl_context():
    ctx = ssl.create_default_context(cafile=tls_mod.bundle_path())
    certs = ctx.get_ca_certs()
    assert len(certs) > 100, len(certs)


def test_forum_api_session_uses_bundle():
    """修复点：ForumApi 必须显式带上可信证书，不能靠 certifi 默认值。"""
    from app import api as api_mod
    client = api_mod.ForumApi()
    try:
        assert client.session.verify == tls_mod.bundle_path()
    finally:
        client.session.close()


# ────────────────────── 联网（需 --online） ──────────────────────


def test_online_bundled_ca_verifies_production_host():
    if not ONLINE:
        return
    import requests
    response = requests.get(constants.BASE_URL + "/healthz",
                            timeout=(5, 15),
                            verify=tls_mod.bundle_path())
    assert response.status_code < 500, response.status_code
