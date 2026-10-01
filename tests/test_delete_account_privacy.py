# -*- coding: utf-8 -*-
"""回归用例：楼中楼渲染 / 隐私政策 v2.0 文案 / 注销账号接口。

对应本次改动：

* ``CommentList._rebuild`` 必须把子回复塞回父条目（否则楼中楼永不渲染）
* ``app.pages.misc`` 隐私政策换成三端唯一真源 v2.0 的 [通用] + [WIN] 段
* ``ForumApi.send_delete_account_code`` / ``delete_account`` 的路径与请求体
"""

from __future__ import annotations

import os
import tempfile

from PyQt6.QtWidgets import QApplication

from app import constants

_app = None


def _app_instance():
    global _app
    if _app is None:
        _app = QApplication.instance() or QApplication([])
    return _app


# ────────────────────── 楼中楼渲染（Task A 回归） ──────────────────────


def test_comment_list_renders_children():
    _app_instance()
    from app.widgets import CommentList
    comments = [
        {"id": "C1", "parent_id": None, "user_id": "U1", "user_name": "楼主",
         "content": "根评论", "created_at": "2026-01-01 00:00:00"},
        {"id": "C2", "parent_id": "C1", "user_id": "U2", "user_name": "甲",
         "content": "子回复", "created_at": "2026-01-01 00:01:00"},
        {"id": "C3", "parent_id": "C2", "user_id": "U3", "user_name": "乙",
         "content": "孙回复", "created_at": "2026-01-01 00:02:00"},
    ]
    listing = CommentList(collapsible=False)
    listing.set_comments(comments, me_id="U1", post_link="PS1")
    root = listing.item_for("C1")
    assert root is not None
    kids = [item.comment_id for item in root.children()]
    assert "C2" in kids, kids                      # 子回复必须挂到父条目
    # 第 3 层（孙级）压平到第 2 层：成为根评论的直接子块，与 C2 同级
    assert "C3" in kids, kids
    child = listing.item_for("C2")
    assert child is not None
    assert child.children() == [], "第 2 层不应再嵌套孙级"
    assert child.data.get("reply_to_name") == ""   # 直接回复根评论：不显示 @
    grand = listing.item_for("C3")
    assert grand is not None                       # items() 递归可达
    assert grand.data.get("reply_to_name") == "甲"  # 压平项显示「回复 @甲」


# ────────────────────── 隐私政策 v2.0（Task D 回归） ──────────────────────


def test_privacy_blocks_cover_chapters_and_contacts():
    from app.pages import misc
    assert not hasattr(misc, "_PRIVACY_PARAGRAPHS"), "旧版隐私段落常量应已移除"
    blocks = misc._PRIVACY_BLOCKS
    headings = [text for kind, text in blocks if kind in ("h2", "h3")]
    body = "\n".join(text for _kind, text in blocks)
    # 第1~十共十个章节标题必须都在
    for num in ("一、", "二、", "三、", "四、", "五、",
                "六、", "七、", "八、", "九、", "十、"):
        assert any(text.startswith(num) for text in headings), num
    # 三端唯一真源只保留 [WIN] 段：3.1 Windows 客户端，丢弃 3.2/3.3
    assert "3.1 Windows 客户端" in headings
    assert not any(text.startswith("3.2") or text.startswith("3.3")
                   for text in headings)
    # 联系信息 / 生效日期 / 版本 必须齐全
    assert "3890320020@qq.com" in body
    assert "https://github.com/crazying-dev" in body
    assert "https://crazying-dev.top" in body
    assert "2026 年 10 月 1 日" in body
    assert "版本：2.0" in body
    # 端标记已剥净，Markdown 表格语法不残留
    for marker in ("[通用]", "[WIN]", "[WEB]", "[ANDROID]"):
        assert marker not in body, marker
    assert "| --- |" not in body
    # 注销账号说明来自「八、你的权利」
    assert "注销账号" in body and "匿名化保留" in body


# ────────────────────── 注销账号接口（Task E 回归） ──────────────────────


def test_delete_account_api_paths_and_body():
    from app import api as api_mod
    from app import session_store
    client = api_mod.ForumApi(store=session_store.SessionStore(
        os.path.join(tempfile.mkdtemp(), "account.bin")))
    calls: list[tuple] = []

    def _fake_request(method, path, **kwargs):
        calls.append((method, path, kwargs.get("json_body")))
        return api_mod.Result(200, {"success": True, "mode": "purge"})

    client.request = _fake_request  # type: ignore[assignment]

    # 1) 发送注销验证码
    sent = client.send_delete_account_code()
    assert sent.ok
    method, path, _body = calls[-1]
    assert method == "POST" and path == "/api/email/send-delete-account-code"

    # 2) 密码方式（purge）
    client._user = {"id": "RL1", "name": "小黑"}
    client.delete_account("purge", password="pw")
    method, path, body = calls[-1]
    assert method == "POST" and path == "/api/user/delete"
    assert constants.DELETE_ACCOUNT_CONFIRM_TEXT == "注销账号"
    assert body == {"mode": "purge",
                    "confirm": constants.DELETE_ACCOUNT_CONFIRM_TEXT,
                    "password": "pw"}
    assert client.user is None, "注销成功后本地登录态应被清空"

    # 3) 验证码方式（anonymize）
    client._user = {"id": "RL1", "name": "小黑"}
    client.delete_account("anonymize", code="123456")
    _method, path, body = calls[-1]
    assert path == "/api/user/delete"
    assert body == {"mode": "anonymize", "confirm": "注销账号", "code": "123456"}
    assert "password" not in body, "未提供密码时不应入参"


def test_delete_account_dialog_defaults():
    _app_instance()
    from app.widgets import DeleteAccountDialog
    dlg = DeleteAccountDialog(None)
    try:
        assert dlg.deleted is False
        assert dlg._mode() == "purge"            # 默认「彻底删除」
        assert dlg.verify_password.isChecked()   # 默认密码验证
        assert dlg.password_input.isEnabled()
        assert not dlg.code_input.isEnabled()    # 选密码时验证码框应禁用
        assert dlg.confirm_input.placeholderText() == "请输入「注销账号」以确认"
    finally:
        dlg.deleteLater()
