"""帖子相关 API（挂载前缀 /api/posts）。

接口：
    GET  /api/posts                帖子列表（page/page_size/category）
    GET  /api/posts/random         随机帖子
    GET  /api/posts/<post_id>      帖子详情（含评论、点赞/收藏状态，浏览量+1）
    POST /api/posts/create         发布帖子（需登录）
    POST /api/posts/<post_id>/like 点赞/取消点赞（需登录）
    POST /api/posts/<post_id>/favorite 收藏/取消收藏（需登录）
    POST /api/posts/<post_id>/report   举报帖子（需登录）
    POST /api/posts/<post_id>/delete   删除帖子（作者本人，需登录）
"""
from __future__ import annotations

import threading

from flask import Blueprint, request, jsonify, g

import db
from api.user import login_required

post_bp = Blueprint("post", __name__)

_CATEGORY_NAME_MAP = {
    "general": "综合",
    "叶羽": "叶羽",
    "创意": "创意",
    "求助": "求助",
    # V1 存量分类兼容
    "talk": "闲聊",
    "question": "求助",
    "share": "分享",
    "creative": "创作",
}


def _notify_fans_new_post_async(author_id, author_name, post_id, title, category):
    """后台线程：向粉丝群发「新帖通知」邮件；任何失败静默忽略。"""
    try:
        import config
        from Email import send_email, build_email_html
        fans = db.follow.get_follower_emails(author_id, limit=5000)
        emails = [f["email"] for f in fans if f.get("email") and f.get("id") != author_id]
        if not emails:
            return
        category_name = _CATEGORY_NAME_MAP.get(category, category or "综合讨论")
        base = config.SITE_BASE_URL.rstrip("/")
        post_url = f"{base}/post/{post_id}"
        plain_title = (title or "").strip()
        plain_body = (
            f"亲爱的粉丝，您好！\n\n"
            f"你关注的用户「{author_name}」刚刚发布了一篇新帖子：\n"
            f"分类：{category_name}\n标题：{plain_title}\n\n"
            f"点击链接立即查看：{post_url}\n\n© 2026 妖精论坛 - 粉丝公益创作"
        )
        html_body = build_email_html(
            label="新帖通知",
            title=f"你关注的 {author_name} 发布了新帖子",
            body_lines=[
                "亲爱的粉丝，您好！",
                f'你关注的用户「<strong style="color:#6A8C89;">{author_name}</strong>」刚刚发布了一篇新帖子。',
                f"分类：{category_name}",
                f"标题：<strong>{plain_title}</strong>",
            ],
            action_text="点击查看新帖子",
            action_url=post_url,
        )
        for i in range(0, len(emails), 100):
            send_email(
                f"【妖精论坛】你关注的 {author_name} 发布了新帖子",
                plain_body,
                receiver_list=emails[i:i + 100],
                html_content=html_body,
            )
    except Exception:
        pass


@post_bp.route("/", methods=["GET"], strict_slashes=False)
def api_post_list():
    page = max(request.args.get("page", 1, type=int), 1)
    page_size = min(max(request.args.get("page_size", 20, type=int), 1), 100)
    category = request.args.get("category") or None
    sort = request.args.get("sort") or "time"
    if sort not in ("time", "comprehensive", "random"):
        sort = "time"
    posts = db.post.get_post_list(page, page_size, category, sort)
    return jsonify({"success": True, "posts": posts, "page": page, "page_size": page_size})


@post_bp.route("/random", methods=["GET"])
def api_post_random():
    limit = max(1, min(request.args.get("limit", 200, type=int), 500))
    posts = db.post.get_random_posts(limit=limit)
    return jsonify({"success": True, "posts": posts})


@post_bp.route("/<post_id>", methods=["GET"])
def api_post_detail(post_id):
    post = db.post.get_post(post_id)
    if not post:
        return jsonify({"success": False, "message": "帖子不存在"}), 404
    comments = db.comment.get_post_comments(post_id, 1, 50)
    db.post.increment_post_views(post_id)
    post["views"] = (post.get("views") or 0) + 1
    user = getattr(g, "user", None)
    uid = user.get("id") if user else None
    liked = db.post.has_liked_post(post_id, uid) if uid else False
    favorited = db.post.has_favorited_post(post_id, uid) if uid else False
    return jsonify({
        "success": True,
        "post": post,
        "comments": comments,
        "liked": liked,
        "favorited": favorited,
    })


@post_bp.route("/create", methods=["POST"])
@login_required
def api_post_create():
    data = request.get_json(silent=True) or {}
    title = (data.get("title") or "").strip()
    content = (data.get("content") or "").strip()
    category = (data.get("category") or "general").strip()
    if not title:
        return jsonify({"success": False, "message": "标题不能为空"}), 400
    if len(title) > 100:
        return jsonify({"success": False, "message": "标题过长（最多100字）"}), 400
    if not content:
        return jsonify({"success": False, "message": "内容不能为空"}), 400
    result = db.post.create_post(g.user["id"], title, content, category)
    if not result.get("success"):
        return jsonify(result), 400
    # 异步通知粉丝（失败不影响发布）
    try:
        t = threading.Thread(
            target=_notify_fans_new_post_async,
            args=(g.user["id"], g.user["name"], result["id"], title, category),
            daemon=True,
        )
        t.start()
    except Exception:
        pass
    return jsonify({"success": True, "id": result["id"]})


@post_bp.route("/<post_id>/like", methods=["POST"])
@login_required
def api_post_like(post_id):
    if not db.post.get_post(post_id):
        return jsonify({"success": False, "message": "帖子不存在"}), 404
    return jsonify(db.post.like_post(post_id, g.user["id"]))


@post_bp.route("/<post_id>/favorite", methods=["POST"])
@login_required
def api_post_favorite(post_id):
    if not db.post.get_post(post_id):
        return jsonify({"success": False, "message": "帖子不存在"}), 404
    return jsonify(db.post.toggle_favorite(post_id, g.user["id"]))


@post_bp.route("/<post_id>/report", methods=["POST"])
@login_required
def api_post_report(post_id):
    data = request.get_json(silent=True) or {}
    reason = (data.get("reason") or "").strip()
    detail = (data.get("detail") or "").strip()
    if not reason:
        return jsonify({"success": False, "message": "请选择举报原因"}), 400
    if len(detail) > 500:
        return jsonify({"success": False, "message": "描述过长（最多500字）"}), 400
    if not db.post.get_post(post_id):
        return jsonify({"success": False, "message": "帖子不存在"}), 404
    return jsonify(db.post.report_post(post_id, g.user["id"], reason, detail))


@post_bp.route("/<post_id>/delete", methods=["POST"])
@login_required
def api_post_delete(post_id):
    result = db.post.delete_post(post_id, g.user["id"])
    if not result.get("success"):
        code = 404 if "不存在" in result.get("message", "") else 403
        return jsonify(result), code
    return jsonify({"success": True})
