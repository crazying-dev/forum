"""Bug 反馈 API（挂载前缀 /api）。

接口：
    POST /api/report-bug  提交 Bug 举报（游客可提交，登录用户自动记录身份）
"""
from __future__ import annotations

from flask import Blueprint, request, jsonify, g

import db
from api.ratelimit import rate_limit

bug_bp = Blueprint("bug", __name__)


@bug_bp.route("/report-bug", methods=["POST"])
def api_report_bug():
    if rate_limit("bug_report", 5, 300):
        return jsonify({"success": False, "message": "请求过于频繁，请5分钟后再试"}), 429

    data = request.get_json(silent=True) or {}
    title = (data.get("title") or "").strip()
    detail = (data.get("detail") or "").strip()
    steps = (data.get("steps") or "").strip()
    contact = (data.get("contact") or "").strip()
    page_url = (data.get("page_url") or "").strip()

    if not title:
        return jsonify({"success": False, "message": "请填写 Bug 标题"}), 400
    if len(title) > 200:
        return jsonify({"success": False, "message": "标题过长（最多200字）"}), 400
    if not detail:
        return jsonify({"success": False, "message": "请填写 Bug 详细描述"}), 400
    if len(detail) > 5000:
        return jsonify({"success": False, "message": "详细描述过长（最多5000字）"}), 400
    if steps and len(steps) > 3000:
        return jsonify({"success": False, "message": "复现步骤过长（最多3000字）"}), 400
    if contact and len(contact) > 200:
        return jsonify({"success": False, "message": "联系方式过长（最多200字）"}), 400

    user = getattr(g, "user", None)
    reporter_id = user.get("id") if user else None
    reporter_name = user.get("name") if user else ""
    user_agent = request.headers.get("User-Agent", "") or ""

    result = db.bug.report_bug(
        title=title,
        detail=detail,
        steps=steps,
        contact=contact,
        reporter_id=reporter_id,
        reporter_name=reporter_name,
        user_agent=user_agent,
        page_url=page_url,
    )
    if not result.get("success"):
        return jsonify(result), 400
    return jsonify({"success": True, "message": "Bug 已提交，感谢反馈", "id": result.get("id")})
