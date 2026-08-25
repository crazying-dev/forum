"""用户相关 API 路由（Blueprint）。

接口列表：
    POST /api/user/login      登录（写 cookie: token + ID）
    POST /api/user/logout     登出（清 cookie）
    POST /api/user/register   注册
    GET  /api/user/info       获取当前登录用户信息
    PUT  /api/user/info       更新当前用户基础资料
    POST /api/user/password   修改密码
    GET  /api/user/<id>       公开查询某个用户资料
"""
from __future__ import annotations

import os
import time
from functools import wraps
from typing import Callable

import re  # noqa: F401 — 用于 age 格式校验与本文件其他正则

from flask import Blueprint, request, jsonify, g, make_response

import config
import db
import tool
from api.encrypt import (
    generate_login_token,
    verify_login_token,
    validate_password,
    validate_username,
    is_valid_email,
)

user_bp = Blueprint("user", __name__)


# ──────────────────────────────────────────────
# 工具：获取真实客户端 IP
# ──────────────────────────────────────────────
def _client_ip() -> str:
    """优先取 X-Forwarded-For，兜底 remote_addr。"""
    forwarded = request.headers.get("X-Forwarded-For", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.remote_addr or "0.0.0.0"


# ──────────────────────────────────────────────
# 工具：cookie 写入（仅 token + ID 两个）
# ──────────────────────────────────────────────
def _set_auth_cookies(resp, token_full: str, user_id: str):
    """按约束写入两个 cookie：token、ID。"""
    common = {
        "path": config.COOKIE_PATH,
        "httponly": config.COOKIE_HTTPONLY,
        "secure": config.COOKIE_SECURE,
        "samesite": config.COOKIE_SAMESITE,
        "max_age": config.TOKEN_TTL_SECONDS,
    }
    if config.COOKIE_DOMAIN:
        common["domain"] = config.COOKIE_DOMAIN
    resp.set_cookie(config.TOKEN_COOKIE_NAME, token_full, **common)
    resp.set_cookie(config.ID_COOKIE_NAME, user_id, **common)


def _clear_auth_cookies(resp):
    common = {
        "path": config.COOKIE_PATH,
        "httponly": config.COOKIE_HTTPONLY,
        "secure": config.COOKIE_SECURE,
        "samesite": config.COOKIE_SAMESITE,
        "expires": 0,
    }
    if config.COOKIE_DOMAIN:
        common["domain"] = config.COOKIE_DOMAIN
    resp.delete_cookie(config.TOKEN_COOKIE_NAME, path=config.COOKIE_PATH, domain=config.COOKIE_DOMAIN)
    resp.delete_cookie(config.ID_COOKIE_NAME, path=config.COOKIE_PATH, domain=config.COOKIE_DOMAIN)


# ──────────────────────────────────────────────
# 工具：鉴权中间件 —— 从 cookie 取 token/ID，验证挂到 g.user
# ──────────────────────────────────────────────
def _authenticate_from_cookies():
    """把当前请求的用户挂到 g.user（成功）或 g.user=None（失败）。"""
    token = request.cookies.get(config.TOKEN_COOKIE_NAME)
    uid = request.cookies.get(config.ID_COOKIE_NAME)
    if not token or not uid:
        g.user = None
        return
    user = db.user.get_user_by_id(uid)
    if not user or user.get("is_banned"):
        g.user = None
        return
    ok = verify_login_token(
        user_id=uid,
        cookie_token=token,
        password_hash=user.get("password") or "",
        client_ip=_client_ip(),
        ttl_seconds=config.TOKEN_TTL_SECONDS,
    )
    g.user = user if ok else None


def _strip_user_public(user: dict | None) -> dict | None:
    """去掉密码哈希，返回前端安全可见的公开字段。"""
    if not user:
        return None
    return {
        "id": user.get("id"),
        "name": user.get("name"),
        "avatar": user.get("avatar"),
        "email": user.get("email"),
        "gender": user.get("gender", 0),
        "age": user.get("age") or "",
        "intro": user.get("intro") or "",
        "vip": user.get("vip") or "0",
        "prefix": user.get("prefix") or "",
        "email_verified": user.get("email_verified", 0),
        "created_at": user.get("created_at"),
        "last_login": user.get("last_login"),
    }


def login_required(fn: Callable) -> Callable:
    """装饰器：要求用户已登录，否则返回 401。"""
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not getattr(g, "user", None):
            return jsonify({"success": False, "message": "请先登录"}), 401
        return fn(*args, **kwargs)
    return wrapper


# ──────────────────────────────────────────────
# 1. 登录
# ──────────────────────────────────────────────
@user_bp.route("/login", methods=["POST"])
def api_user_login():
    """
    Body(JSON):
        password:  str (必填)
        name:      str (可选，用户名或邮箱二选一)
        email:     str (可选，用户名或邮箱二选一)
    """
    data = request.get_json(silent=True) or {}
    tool.GETIP(_client_ip())

    password = data.get("password")
    name = (data.get("name") or "").strip() or None
    email = (data.get("email") or "").strip() or None

    if not password:
        return jsonify({"success": False, "message": "用户名或密码错误"}), 401
    identifier = name or email
    if not identifier:
        return jsonify({"success": False, "message": "用户名或密码错误"}), 401

    userinfo = db.user.LoginINFOTrueorFlase(identifier, password, _client_ip())
    if not userinfo:
        return jsonify({"success": False, "message": "用户名或密码错误"}), 401

    # 生成 token（按已有算法），写 cookie：仅 token + ID
    token_full, core, st = generate_login_token(
        user_id=userinfo["id"],
        password_hash=userinfo["password"],
        client_ip=_client_ip(),
    )
    public_user = _strip_user_public(userinfo)
    resp = make_response(jsonify({
        "success": True,
        "message": "登录成功",
        "Token": f"token---{core}---{st}",   # 与接口原有命名/格式兼容
        "user": public_user,
    }))
    _set_auth_cookies(resp, token_full, userinfo["id"])
    return resp


# ──────────────────────────────────────────────
# 2. 登出
# ──────────────────────────────────────────────
@user_bp.route("/logout", methods=["POST"])
def api_user_logout():
    resp = make_response(jsonify({"success": True, "message": "已退出登录"}))
    _clear_auth_cookies(resp)
    return resp


# ──────────────────────────────────────────────
# 3. 注册
# ──────────────────────────────────────────────
@user_bp.route("/register", methods=["POST"])
def api_user_register():
    """
    Body(JSON):
        name:     str  2-20 字符
        email:    str  合法邮箱
        password: str  ≥8 位，含字母+数字
    """
    data = request.get_json(silent=True) or {}
    tool.GETIP(_client_ip())

    name = (data.get("name") or "").strip()
    email = (data.get("email") or "").strip()
    password = data.get("password") or ""

    ok, msg = validate_username(name)
    if not ok:
        return jsonify({"success": False, "message": msg}), 400
    if not is_valid_email(email):
        return jsonify({"success": False, "message": "请输入有效的邮箱"}), 400
    ok, msg = validate_password(password)
    if not ok:
        return jsonify({"success": False, "message": msg}), 400

    result = db.user.create_user(name=name, email=email, raw_password=password)
    if not result.get("success"):
        return jsonify(result), 400

    # 注册即登录：查回用户记录，生成 token 写 cookie
    user = db.user.get_user_by_id(result["id"])
    if user:
        token_full, core, st = generate_login_token(
            user_id=user["id"],
            password_hash=user["password"],
            client_ip=_client_ip(),
        )
        resp = make_response(jsonify({
            "success": True,
            "message": "注册成功",
            "id": result["id"],
            "avatar": result["avatar"],
            "Token": f"token---{core}---{st}",
            "user": _strip_user_public(user),
        }), 200)
        _set_auth_cookies(resp, token_full, user["id"])
        return resp

    return jsonify({
        "success": True,
        "message": "注册成功",
        "id": result["id"],
        "avatar": result["avatar"],
    }), 200


# ──────────────────────────────────────────────
# 4. 当前用户信息（需登录）
# ──────────────────────────────────────────────
@user_bp.route("/info", methods=["GET"])
@login_required
def api_user_info():
    user = _strip_user_public(g.user)
    user["stats"] = _build_user_stats(g.user["id"])
    return jsonify({"success": True, "user": user}), 200


# ──────────────────────────────────────────────
# 5. 更新当前用户信息（需登录）
# ──────────────────────────────────────────────
@user_bp.route("/info", methods=["PUT", "POST"])
@login_required
def api_user_update():
    data = request.get_json(silent=True) or {}
    # 允许更新的字段白名单
    payload = {}
    if "avatar" in data and isinstance(data["avatar"], str):
        payload["avatar"] = data["avatar"].strip()
    if "gender" in data:
        try:
            payload["gender"] = int(data["gender"])
        except (ValueError, TypeError):
            pass
    if "age" in data and isinstance(data["age"], str):
        age_raw = data["age"].strip()
        if age_raw:
            # 允许：纯数字年龄、YYYY-MM-DD 日期、YYYY/MM/DD（兼容不同前端组件输出）
            if not re.fullmatch(r"\d{1,3}", age_raw) and \
               not re.fullmatch(r"\d{4}[-/]\d{1,2}[-/]\d{1,2}", age_raw):
                return jsonify({"success": False, "message": "年龄格式不正确（数字或 YYYY-MM-DD）"}), 400
            payload["age"] = age_raw[:32]
        else:
            payload["age"] = None  # 清空年龄（兼容线上 INTEGER 列）
    if "intro" in data and isinstance(data["intro"], str):
        payload["intro"] = data["intro"].strip()
    if "name" in data and isinstance(data["name"], str):
        name = data["name"].strip()
        ok, msg = validate_username(name)
        if not ok:
            return jsonify({"success": False, "message": msg}), 400
        payload["name"] = name
    if "prefix" in data and isinstance(data["prefix"], str):
        payload["prefix"] = data["prefix"].strip()[:32]

    if not payload:
        return jsonify({"success": False, "message": "没有可更新的字段"}), 400

    ok, msg = db.user.update_user(g.user["id"], **payload)
    if not ok:
        return jsonify({"success": False, "message": msg}), 400
    # 刷新信息返回
    refreshed = db.user.get_user_by_id(g.user["id"])
    return jsonify({"success": True, "message": msg, "user": _strip_user_public(refreshed)}), 200


# ──────────────────────────────────────────────
# 6. 修改密码（需登录，需验证原密码）
# ──────────────────────────────────────────────
@user_bp.route("/password", methods=["POST"])
@login_required
def api_user_change_password():
    data = request.get_json(silent=True) or {}
    old_raw = data.get("old_password") or ""
    new_raw = data.get("new_password") or ""

    ok, msg = validate_password(new_raw)
    if not ok:
        return jsonify({"success": False, "message": msg}), 400
    if old_raw == new_raw:
        return jsonify({"success": False, "message": "新密码不能与旧密码相同"}), 400

    ok, msg = db.user.change_password(g.user["id"], old_raw, new_raw)
    if not ok:
        return jsonify({"success": False, "message": msg}), 400
    # 改密后重新登录更安全：清理 cookie，要求重新登录
    resp = make_response(jsonify({"success": True, "message": msg}))
    _clear_auth_cookies(resp)
    return resp


# ──────────────────────────────────────────────
# 7. 按 ID 查询任意用户公开资料（无需登录）
# ──────────────────────────────────────────────
@user_bp.route("/<user_id>", methods=["GET"])
def api_user_public(user_id: str):
    user = db.user.get_user_by_id(user_id.strip())
    if not user or user.get("is_banned"):
        return jsonify({"success": False, "message": "用户不存在"}), 404
    public = _strip_user_public(user)
    public.pop("email", None)  # 公开资料隐藏 email
    public["stats"] = _build_user_stats(user["id"])
    viewer = getattr(g, "user", None)
    viewer_id = viewer.get("id") if viewer else None
    public["is_following"] = bool(viewer_id) and db.follow.is_following(viewer_id, user["id"])
    public["is_self"] = viewer_id == user["id"]
    return jsonify({"success": True, "user": public}), 200


# ══════════════════════════════════════════════════════════════
# 以下为 forum-new 全量 API 追加：头像上传 / 用户社交 / 统计
# ══════════════════════════════════════════════════════════════

import io as _io


def _build_user_stats(user_id):
    """合并帖子统计 + 关注统计。"""
    stats = db.post.get_user_stats(user_id)
    follow_stats = db.follow.get_follow_stats(user_id)
    return {**stats, **follow_stats}


# ── 8. 上传头像（保存本地 /root/db/avatar，经 /avatar/<file> 访问；与 v1 一致）──
@user_bp.route("/avatar/upload", methods=["POST"])
@login_required
def api_user_avatar_upload():
    file = request.files.get("avatar")
    if not file or not file.filename:
        return jsonify({"success": False, "message": "请选择图片"}), 400
    raw = file.read()
    if len(raw) > config.AVATAR_MAX_BYTES:
        return jsonify({"success": False, "message": "图片过大（最大5MB）"}), 400

    # 裁剪压缩为 400×400 WebP（质量85）
    try:
        from PIL import Image
        img = Image.open(_io.BytesIO(raw))
        img = img.convert("RGBA")
        bg = Image.new("RGBA", img.size, (255, 255, 255, 255))
        bg.paste(img, mask=img.split()[3] if img.mode == "RGBA" else None)
        img.close()
        img = bg.convert("RGB")
        bg.close()
        img = img.resize((400, 400), Image.LANCZOS)
        buf = _io.BytesIO()
        img.save(buf, format="WEBP", quality=85)
        webp_data = buf.getvalue()
        img.close()
        buf.close()
    except Exception:
        return jsonify({"success": False, "message": "图片处理失败，请上传有效图片"}), 400

    # 保存到本地头像目录（/avatar/<file> 静态路由指向此处）
    import uuid as _uuid
    avatar_dir = config.AVATAR_UPLOAD_DIR
    try:
        os.makedirs(avatar_dir, exist_ok=True)
        avatar_id = str(_uuid.uuid4())
        avatar_path = os.path.join(avatar_dir, f"{avatar_id}.webp")
        with open(avatar_path, "wb") as f:
            f.write(webp_data)
    except Exception as e:
        return jsonify({"success": False, "message": f"头像保存失败: {e}"}), 500

    avatar_url = f"/avatar/{avatar_id}.webp"
    ok, msg = db.user.update_user(g.user["id"], avatar=avatar_url)
    if not ok:
        return jsonify({"success": False, "message": msg}), 400
    return jsonify({"success": True, "avatar": avatar_url})


# ── 9. 关注 / 取消关注（需登录）──
@user_bp.route("/<user_id>/follow", methods=["POST"])
@login_required
def api_user_follow(user_id):
    target = db.user.get_user_by_id(user_id.strip())
    if not target or target.get("is_banned"):
        return jsonify({"success": False, "message": "用户不存在"}), 404
    result = db.follow.toggle_follow(g.user["id"], target["id"])
    if not result.get("success"):
        return jsonify(result), 400
    return jsonify(result)


# ── 10. 关注列表 / 粉丝列表（公开，登录者视角标注 is_following/is_self）──
def _annotate_user_list(users):
    viewer = getattr(g, "user", None)
    viewer_id = viewer.get("id") if viewer else None
    for u in users:
        u["is_following"] = bool(viewer_id) and db.follow.is_following(viewer_id, u["id"])
        u["is_self"] = viewer_id == u["id"]
    return users


@user_bp.route("/<user_id>/posts", methods=["GET"])
def api_user_posts(user_id):
    """获取指定用户的帖子列表（公开）。"""
    user = db.user.get_user_by_id(user_id.strip())
    if not user or user.get("is_banned"):
        return jsonify({"success": False, "message": "用户不存在"}), 404
    page = max(request.args.get("page", 1, type=int), 1)
    page_size = min(max(request.args.get("page_size", 20, type=int), 1), 100)
    posts = db.post.get_user_posts(user["id"], page, page_size)
    return jsonify({"success": True, "posts": posts, "page": page, "page_size": page_size})


@user_bp.route("/<user_id>/favorites", methods=["GET"])
def api_user_favorites(user_id):
    """获取指定用户收藏的帖子列表（仅本人可查）。"""
    user = db.user.get_user_by_id(user_id.strip())
    if not user or user.get("is_banned"):
        return jsonify({"success": False, "message": "用户不存在"}), 404
    viewer = getattr(g, "user", None)
    if not viewer or viewer.get("id") != user["id"]:
        return jsonify({"success": False, "message": "无权查看他人收藏"}), 403
    page = max(request.args.get("page", 1, type=int), 1)
    page_size = min(max(request.args.get("page_size", 20, type=int), 1), 100)
    posts = db.post.get_user_favorites(user["id"], page, page_size)
    return jsonify({"success": True, "posts": posts, "page": page, "page_size": page_size})


@user_bp.route("/<user_id>/following", methods=["GET"])
def api_user_following(user_id):
    user = db.user.get_user_by_id(user_id.strip())
    if not user or user.get("is_banned"):
        return jsonify({"success": False, "message": "用户不存在"}), 404
    page = max(request.args.get("page", 1, type=int), 1)
    page_size = min(max(request.args.get("page_size", 20, type=int), 1), 100)
    users = db.follow.get_following_list(user["id"], page, page_size)
    return jsonify({
        "success": True,
        "users": _annotate_user_list(users),
        "page": page,
        "page_size": page_size,
    })


@user_bp.route("/<user_id>/followers", methods=["GET"])
def api_user_followers(user_id):
    user = db.user.get_user_by_id(user_id.strip())
    if not user or user.get("is_banned"):
        return jsonify({"success": False, "message": "用户不存在"}), 404
    page = max(request.args.get("page", 1, type=int), 1)
    page_size = min(max(request.args.get("page_size", 20, type=int), 1), 100)
    users = db.follow.get_follower_list(user["id"], page, page_size)
    return jsonify({
        "success": True,
        "users": _annotate_user_list(users),
        "page": page,
        "page_size": page_size,
    })


# ── 11. 指定用户的评论列表（公开）──
@user_bp.route("/<user_id>/comments", methods=["GET"])
def api_user_comments(user_id):
    """获取指定用户的所有评论（附带 post_id/post_title 用于跳转锚点）。"""
    user = db.user.get_user_by_id(user_id.strip())
    if not user or user.get("is_banned"):
        return jsonify({"success": False, "message": "用户不存在"}), 404
    page = max(request.args.get("page", 1, type=int), 1)
    page_size = min(max(request.args.get("page_size", 20, type=int), 1), 100)
    comments, total = db.comment.get_user_comments(user["id"], page, page_size)
    return jsonify({
        "success": True,
        "comments": comments,
        "total": total,
        "page": page,
        "page_size": page_size,
    })
