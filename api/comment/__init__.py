"""评论相关 API（挂载前缀 /api，路径兼容原 forum：/api/posts/<id>/comments* 与 /api/comments/*）。

接口：
    GET  /api/posts/<post_id>/comments         获取帖子评论（page/page_size）
    POST /api/posts/<post_id>/comments/create  发表评论（需登录，parent_id 支持楼中楼）
    POST /api/comments/<comment_id>/delete     删除评论（作者本人，需登录）
"""
from __future__ import annotations

from flask import Blueprint, request, jsonify, g

import db
from api.user import login_required

comment_bp = Blueprint("comment", __name__)


@comment_bp.route("/posts/<post_id>/comments", methods=["GET"])
def api_post_comments(post_id):
    page = max(request.args.get("page", 1, type=int), 1)
    page_size = min(max(request.args.get("page_size", 50, type=int), 1), 100)
    if not db.post.get_post(post_id):
        return jsonify({"success": False, "message": "帖子不存在"}), 404
    comments = db.comment.get_post_comments(post_id, page, page_size)
    return jsonify({"success": True, "comments": comments, "page": page, "page_size": page_size})


@comment_bp.route("/posts/<post_id>/comments/create", methods=["POST"])
@login_required
def api_comment_create(post_id):
    data = request.get_json(silent=True) or {}
    content = (data.get("content") or "").strip()
    parent_id = data.get("parent_id") or None
    if not content:
        return jsonify({"success": False, "message": "评论内容不能为空"}), 400
    if len(content) > 500:
        return jsonify({"success": False, "message": "评论过长（最多500字）"}), 400
    if not db.post.get_post(post_id):
        return jsonify({"success": False, "message": "帖子不存在"}), 404
    result = db.comment.add_comment(post_id, g.user["id"], content, parent_id)
    if not result.get("success"):
        return jsonify(result), 400
    return jsonify({"success": True, "comment": result["comment"]})


@comment_bp.route("/comments/<comment_id>/delete", methods=["POST"])
@login_required
def api_comment_delete(comment_id):
    result = db.comment.delete_comment(comment_id, g.user["id"])
    if not result.get("success"):
        code = 404 if "不存在" in result.get("message", "") else 403
        return jsonify(result), code
    return jsonify({"success": True})


@comment_bp.route("/comments/<comment_id>/report", methods=["POST"])
@login_required
def api_comment_report(comment_id):
    data = request.get_json(silent=True) or {}
    reason = (data.get("reason") or "").strip()
    detail = (data.get("detail") or "").strip()
    if not reason:
        return jsonify({"success": False, "message": "请选择举报原因"}), 400
    if len(detail) > 500:
        return jsonify({"success": False, "message": "描述过长（最多500字）"}), 400
    result = db.comment.report_comment(comment_id, g.user["id"], reason, detail)
    if not result.get("success"):
        code = 404 if "不存在" in result.get("message", "") else 400
        return jsonify(result), code
    return jsonify(result)


@comment_bp.route("/users/me/replies", methods=["GET"])
@login_required
def api_my_replies():
    """我的回复：回复了我评论的回复列表（V1 迁移）。"""
    page = max(request.args.get("page", 1, type=int), 1)
    page_size = min(max(request.args.get("page_size", 50, type=int), 1), 100)
    result = db.comment.get_replies_to_my_comments(g.user["id"], page, page_size)
    return jsonify({"success": True, **result})
