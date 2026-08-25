"""邮箱验证 / 找回密码 API（挂载前缀 /api）。

接口：
    POST /api/email/send-verify-email   发送邮箱验证邮件（需登录）
    POST /api/email/verify-email        校验验证 token（body: token）
    POST /api/email/send-reset-password 发送重置密码邮件（body: email，防邮箱枚举）
    POST /api/email/reset-password      重置密码（body: token + password）

依赖 SMTP 配置（config.SMTP_*），邮件服务不可用时返回明确错误。
"""
from __future__ import annotations

from flask import Blueprint, request, jsonify, g

import config
import db
from api.encrypt import validate_password, is_valid_email
from api.user import login_required
from Email import send_email, build_email_html

email_bp = Blueprint("email", __name__)


@email_bp.route("/email/send-verify-email", methods=["POST"])
@login_required
def api_send_verify_email():
    user = db.user.get_user_by_id(g.user["id"])
    if not user:
        return jsonify({"success": False, "message": "用户不存在"}), 404
    if user.get("email_verified"):
        return jsonify({"success": False, "message": "邮箱已验证，无需重复验证"}), 400

    token_result = db.verify.create_verify_token(
        user["id"], "email_verify", config.VERIFY_TOKEN_EXPIRES_MINUTES
    )
    if not token_result.get("success"):
        return jsonify({"success": False, "message": "生成验证链接失败"}), 500

    token = token_result["token"]
    base = config.SITE_BASE_URL.rstrip("/")
    verify_url = f"{base}/verify-email?token={token}"
    subject = "【妖精论坛】邮箱验证"
    plain = (
        f"尊敬的 {user['name']}，您好！\n\n"
        f"请点击以下链接验证并激活您的邮箱地址：\n{verify_url}\n\n"
        f"验证链接有效期为 {config.VERIFY_TOKEN_EXPIRES_MINUTES} 分钟。\n"
        f"© 2026 妖精论坛 - 粉丝公益创作"
    )
    html = build_email_html(
        label="邮箱验证",
        title="验证您的邮箱地址",
        body_lines=[
            f"尊敬的 <strong style=\"color:#6A8C89;\">{user['name']}</strong>，您好！",
            "请点击下方按钮验证并激活您的邮箱地址。",
            f"验证链接有效期为 {config.VERIFY_TOKEN_EXPIRES_MINUTES} 分钟。",
        ],
        action_text="验证邮箱",
        action_url=verify_url,
    )
    ok, err = send_email(subject, plain, receiver_list=[user["email"]], html_content=html)
    if not ok:
        return jsonify({"success": False, "message": f"邮件服务暂不可用: {err}"}), 503
    return jsonify({"success": True, "message": "验证邮件已发送，请查收邮箱"})


@email_bp.route("/email/verify-email", methods=["POST"])
def api_verify_email():
    data = request.get_json(silent=True) or {}
    token = (data.get("token") or "").strip()
    if not token:
        return jsonify({"success": False, "message": "验证链接无效"}), 400
    info = db.verify.get_verify_token(token, "email_verify")
    if not info:
        return jsonify({"success": False, "message": "验证链接已过期或无效"}), 400
    db.verify.update_user_email_verified(info["user_id"])
    db.verify.delete_verify_token(token)
    return jsonify({"success": True, "message": "邮箱验证成功"})


@email_bp.route("/email/send-reset-password", methods=["POST"])
def api_send_reset_password():
    data = request.get_json(silent=True) or {}
    email = (data.get("email") or "").strip().lower()
    if not is_valid_email(email):
        return jsonify({"success": False, "message": "请输入有效的邮箱"}), 400

    user = db.user.get_user_by_email(email)
    if not user:
        # 防邮箱枚举：无论邮箱是否存在都返回相同信息
        return jsonify({"success": True, "message": "如果该邮箱已注册，重置链接已发送至邮箱"})

    token_result = db.verify.create_verify_token(
        user["id"], "password_reset", config.VERIFY_TOKEN_EXPIRES_MINUTES
    )
    if not token_result.get("success"):
        return jsonify({"success": False, "message": "生成重置链接失败"}), 500

    token = token_result["token"]
    base = config.SITE_BASE_URL.rstrip("/")
    reset_url = f"{base}/reset-password?token={token}"
    subject = "【妖精论坛】重置密码"
    plain = (
        f"尊敬的 {user['name']}，您好！\n\n"
        f"请点击以下链接设置新的密码：\n{reset_url}\n\n"
        f"重置链接有效期为 {config.VERIFY_TOKEN_EXPIRES_MINUTES} 分钟。\n"
        f"如非本人操作，请忽略此邮件。\n\n© 2026 妖精论坛 - 粉丝公益创作"
    )
    html = build_email_html(
        label="重置密码",
        title="重置您的密码",
        body_lines=[
            f"尊敬的 <strong style=\"color:#6A8C89;\">{user['name']}</strong>，您好！",
            "请点击下方按钮设置新的密码。",
            f"重置链接有效期为 {config.VERIFY_TOKEN_EXPIRES_MINUTES} 分钟。",
            "如非本人操作，请忽略此邮件。",
        ],
        action_text="重置密码",
        action_url=reset_url,
    )
    ok, err = send_email(subject, plain, receiver_list=[email], html_content=html)
    if not ok:
        return jsonify({"success": False, "message": f"邮件服务暂不可用: {err}"}), 503
    return jsonify({"success": True, "message": "如果该邮箱已注册，重置链接已发送至邮箱"})


@email_bp.route("/email/reset-password", methods=["POST"])
def api_reset_password():
    data = request.get_json(silent=True) or {}
    token = (data.get("token") or "").strip()
    password = data.get("password") or ""
    if not token:
        return jsonify({"success": False, "message": "重置链接无效"}), 400
    ok, msg = validate_password(password)
    if not ok:
        return jsonify({"success": False, "message": msg}), 400
    info = db.verify.get_verify_token(token, "password_reset")
    if not info:
        return jsonify({"success": False, "message": "重置链接已过期或无效"}), 400
    ok, msg = db.user.reset_password(info["user_id"], password)
    if not ok:
        return jsonify({"success": False, "message": msg}), 400
    db.verify.delete_verify_token(token)
    return jsonify({"success": True, "message": "密码重置成功"})
