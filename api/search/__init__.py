"""搜索 API（挂载前缀 /api）。

接口：
    GET /api/search?k=<关键词>&page=1&page_size=20&type=both|posts|users
"""
from __future__ import annotations

from flask import Blueprint, request, jsonify

import db

search_bp = Blueprint("search", __name__)


@search_bp.route("/search", methods=["GET"])
def api_search():
    keyword = (request.args.get("k") or "").strip()
    page = max(request.args.get("page", 1, type=int), 1)
    page_size = min(max(request.args.get("page_size", 20, type=int), 1), 100)
    search_type = request.args.get("type", "both")
    if search_type not in ("posts", "users", "both"):
        search_type = "both"
    if len(keyword) < 2:
        return jsonify({"success": False, "message": "关键词至少2个字符"}), 400

    result = {
        "success": True,
        "keyword": keyword,
        "page": page,
        "page_size": page_size,
    }
    if search_type in ("posts", "both"):
        posts, posts_total = db.search.search_posts(keyword, page, page_size)
        result["posts"] = posts
        result["posts_total"] = posts_total
        result["posts_has_more"] = (page * page_size) < posts_total
    if search_type in ("users", "both"):
        users, users_total = db.search.search_users(keyword, page, page_size)
        result["users"] = users
        result["users_total"] = users_total
        result["users_has_more"] = (page * page_size) < users_total
    return jsonify(result)
