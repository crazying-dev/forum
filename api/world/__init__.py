"""世界频道 API（挂载前缀 /api/world）。

接口：
    GET  /api/world/ALL   获取最近消息列表
    POST /api/world/Send  发送消息（需登录，每用户 2 秒一条）

注：自 v1.1 起前端改用 HTTP 轮询，不再使用 WebSocket 长连接。
"""
from __future__ import annotations

from flask import Blueprint, request, jsonify, g

import db
from api.user import login_required

world_bp = Blueprint("world", __name__)


@world_bp.route("/ALL", methods=["GET"])
def api_world_all():
    messages = db.world.get_world_messages()
    resp = jsonify(messages)
    resp.headers["Cache-Control"] = "max-age=2"
    return resp


@world_bp.route("/Send", methods=["POST"])
@login_required
def api_world_send():
    data = request.get_json(silent=True) or {}
    content = (data.get("content") or "").strip()
    parent_id = data.get("parent_id") or None
    if not content:
        return jsonify({"success": False, "message": "内容不能为空"}), 400
    if len(content) > 500:
        return jsonify({"success": False, "message": "内容过长（最多500字）"}), 400
    result = db.world.send_world_message(g.user["id"], g.user["name"], content, parent_id)
    if not result.get("success"):
        return jsonify(result), 429 if "太快" in result.get("message", "") else 400
    return jsonify(result)
