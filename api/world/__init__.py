"""世界频道 API（挂载前缀 /api/world）。

接口：
    GET  /api/world/ALL   获取最近消息列表（支持 since 增量）
    POST /api/world/Send  发送消息（需登录，每用户 2 秒一条）

注：自 v1.1 起前端改用 HTTP 轮询，不再使用 WebSocket 长连接。
"""
from __future__ import annotations

import re

from flask import Blueprint, request, jsonify, g

import db
from api.user import login_required

world_bp = Blueprint("world", __name__)

# 增量参数 since 的字面量校验：只接受时间串（日期 / 日期时间 / ISO8601，可带时区）。
# 非法值直接忽略（回落全量），避免把游医字符串丢给数据库做类型转换导致 500。
_SINCE_RE = re.compile(
    r"^\d{4}-\d{2}-\d{2}(?:[ T]\d{2}:\d{2}(?::\d{2}(?:\.\d+)?)?)?(?:Z|[+-]\d{2}:?\d{2})?$"
)


def _parse_since(raw):
    """归一化 since 查询参数；空 / 非法返回 None（回落为全量拉取）。"""
    if not raw:
        return None
    s = str(raw).strip()
    if not s or not _SINCE_RE.match(s):
        return None
    return s


@world_bp.route("/ALL", methods=["GET"])
def api_world_all():
    """最近消息列表。

    查询参数 ``since``（可选）= 客户端已持有的最后一条消息时间；
    传入时仅返回其后（严格晚于）的新消息（增量），不传则返回最近 100 条（全量）。
    """
    messages = db.world.get_world_messages(since=_parse_since(request.args.get("since")))
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
