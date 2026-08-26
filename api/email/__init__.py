"""邮箱验证 / 找回密码 API（挂载前缀 /api）。

接口：
    POST /api/email/send-verify-email   发送邮箱验证邮件（需登录）
    POST /api/email/verify-email        校验验证 token（body: token）
    POST /api/email/send-reset-password 发送重置密码邮件（body: email，防邮箱枚举）
    POST /api/email/reset-password      重置密码（body: token + password）

依赖 SMTP 配置（config.SMTP_*），邮件服务不可用时返回明确错误。
"""
from __future__ import annotations

import random

from flask import Blueprint, request, jsonify, g

import config
import db
from api.encrypt import validate_password, is_valid_email
from api.ratelimit import rate_limit
from api.user import login_required
from Email import send_email, build_email_html

email_bp = Blueprint("email", __name__)


def _random_code() -> str:
    return str(random.randint(100000, 999999))


@email_bp.route("/email/send-verify-email", methods=["POST"])
@login_required
def api_send_verify_email():
    if rate_limit("verify_email", 3, 300):
        return jsonify({"success": False, "message": "请求过于频繁，请5分钟后再试"}), 429
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
    if rate_limit("reset_pwd", 3, 300):
        return jsonify({"success": False, "message": "请求过于频繁，请5分钟后再试"}), 429
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
    if rate_limit("reset_pwd", 5, 300):
        return jsonify({"success": False, "message": "请求过于频繁，请稍后再试"}), 429
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


# ──────────────────────────────────────────────
# 6 位数字验证码：注册 / 邮箱验证 / 验证码重置密码
# ──────────────────────────────────────────────
def _valid_code(code) -> bool:
    return bool(code) and code.isdigit() and len(code) == 6


def _cleanup_codes(email, purpose):
    """清理该邮箱此用途的过期/已用验证码。"""
    try:
        db.execute_query(
            "DELETE FROM verify_codes WHERE email = %s AND purpose = %s "
            "AND (expires_at < CURRENT_TIMESTAMP OR used = 1)",
            (email, purpose),
        )
    except Exception:
        pass


@email_bp.route("/email/send-register-code", methods=["POST"])
def api_send_register_code():
    """发送6位验证码到邮箱用于注册（无需登录）。"""
    if rate_limit("register_code", 3, 300):
        return jsonify({"success": False, "message": "请求过于频繁，请5分钟后再试"}), 429
    data = request.get_json(silent=True) or {}
    email = (data.get("email") or "").strip().lower()
    if not is_valid_email(email):
        return jsonify({"success": False, "message": "请输入有效的邮箱"}), 400
    if db.user.get_user_by_email(email):
        return jsonify({"success": False, "message": "该邮箱已被注册"}), 400

    code = _random_code()
    result = db.verify.create_verify_code(email, code, "register")
    if not result.get("success"):
        return jsonify({"success": False, "message": "生成验证码失败"}), 500

    subject = "【妖精论坛】注册验证码"
    plain = (
        f"感谢您注册妖精论坛！\n\n"
        f"您的注册验证码为：{code}\n\n"
        f"验证码有效期5分钟，请勿泄露给他人。\n"
        f"如非本人操作，请忽略此邮件。\n\n© 2026 妖精论坛 - 粉丝公益创作"
    )
    html = build_email_html(
        label="注册验证码",
        title="感谢您注册妖精论坛",
        body_lines=[
            "您的注册验证码为：",
            f'<div style="font-size:32px;font-weight:700;color:#6A8C89;letter-spacing:6px;text-align:center;padding:12px 0;">{code}</div>',
            "验证码有效期5分钟，请勿泄露给他人。",
            "如非本人操作，请忽略此邮件。",
        ],
    )
    ok, err = send_email(subject, plain, receiver_list=[email], html_content=html)
    if not ok:
        return jsonify({"success": False, "message": f"邮件服务暂不可用: {err}"}), 503
    return jsonify({"success": True, "message": "验证码已发送至邮箱"})


@email_bp.route("/email/send-verify-code", methods=["POST"])
@login_required
def api_send_verify_code():
    """发送6位验证码到当前登录用户的邮箱（用于邮箱验证）。"""
    if rate_limit("verify_code", 3, 300):
        return jsonify({"success": False, "message": "请求过于频繁，请5分钟后再试"}), 429
    user = db.user.get_user_by_id(g.user["id"])
    if not user:
        return jsonify({"success": False, "message": "用户不存在"}), 404
    if user.get("email_verified"):
        return jsonify({"success": False, "message": "邮箱已验证，无需重复验证"}), 400

    email = user["email"]
    code = _random_code()
    result = db.verify.create_verify_code(email, code, "email_verify")
    if not result.get("success"):
        return jsonify({"success": False, "message": "生成验证码失败"}), 500

    subject = "【妖精论坛】邮箱验证码"
    plain = (
        f"尊敬的 {user['name']}，您好！\n\n"
        f"您的邮箱验证码为：{code}\n\n"
        f"验证码有效期5分钟，请勿泄露给他人。\n"
        f"如非本人操作，请忽略此邮件。\n\n© 2026 妖精论坛 - 粉丝公益创作"
    )
    html = build_email_html(
        label="邮箱验证码",
        title="验证您的邮箱",
        body_lines=[
            f"尊敬的 <strong style=\"color:#6A8C89;\">{user['name']}</strong>，您好！",
            "您的邮箱验证码为：",
            f'<div style="font-size:32px;font-weight:700;color:#6A8C89;letter-spacing:6px;text-align:center;padding:12px 0;">{code}</div>',
            "验证码有效期5分钟，请勿泄露给他人。",
            "如非本人操作，请忽略此邮件。",
        ],
    )
    ok, err = send_email(subject, plain, receiver_list=[email], html_content=html)
    if not ok:
        return jsonify({"success": False, "message": f"邮件服务暂不可用: {err}"}), 503
    return jsonify({"success": True, "message": "验证码已发送至邮箱"})


@email_bp.route("/email/verify-code-email", methods=["POST"])
@login_required
def api_verify_code_email():
    """使用6位验证码验证邮箱。"""
    if rate_limit("verify_code", 5, 300):
        return jsonify({"success": False, "message": "请求过于频繁，请稍后再试"}), 429
    user = db.user.get_user_by_id(g.user["id"])
    if not user:
        return jsonify({"success": False, "message": "用户不存在"}), 404

    data = request.get_json(silent=True) or {}
    code = (data.get("code") or "").strip()
    if not _valid_code(code):
        return jsonify({"success": False, "message": "请输入6位数字验证码"}), 400

    email = user["email"]
    code_info = db.verify.get_verify_code(email, code, "email_verify")
    if not code_info:
        db.verify.increment_verify_code_attempts(email, "email_verify")
        return jsonify({"success": False, "message": "验证码无效或已过期"}), 400

    db.verify.update_user_email_verified(user["id"])
    db.verify.mark_verify_code_used(email, code, "email_verify")
    _cleanup_codes(email, "email_verify")
    return jsonify({"success": True, "message": "邮箱验证成功"})


@email_bp.route("/email/send-code-reset-password", methods=["POST"])
def api_send_code_reset_password():
    """发送6位验证码到用户邮箱用于重置密码（防邮箱枚举）。"""
    if rate_limit("reset_pwd_code", 3, 300):
        return jsonify({"success": False, "message": "请求过于频繁，请5分钟后再试"}), 429
    data = request.get_json(silent=True) or {}
    email = (data.get("email") or "").strip().lower()
    if not is_valid_email(email):
        return jsonify({"success": False, "message": "请输入有效的邮箱"}), 400

    user = db.user.get_user_by_email(email)
    if not user:
        return jsonify({"success": True, "message": "如果该邮箱已注册，验证码已发送至邮箱"})

    code = _random_code()
    result = db.verify.create_verify_code(email, code, "password_reset")
    if not result.get("success"):
        return jsonify({"success": False, "message": "生成验证码失败"}), 500

    subject = "【妖精论坛】重置密码验证码"
    plain = (
        f"尊敬的 {user['name']}，您好！\n\n"
        f"您正在请求重置密码，验证码为：{code}\n\n"
        f"验证码有效期5分钟，请勿泄露给他人。\n"
        f"如非本人操作，请忽略此邮件。\n\n© 2026 妖精论坛 - 粉丝公益创作"
    )
    ok, err = send_email(subject, plain, receiver_list=[email])
    if not ok:
        return jsonify({"success": False, "message": f"邮件服务暂不可用: {err}"}), 503
    return jsonify({"success": True, "message": "如果该邮箱已注册，验证码已发送至邮箱"})


@email_bp.route("/email/reset-password-by-code", methods=["POST"])
def api_reset_password_by_code():
    """使用6位验证码重置密码。"""
    if rate_limit("reset_pwd_code", 5, 300):
        return jsonify({"success": False, "message": "请求过于频繁，请稍后再试"}), 429
    data = request.get_json(silent=True) or {}
    email = (data.get("email") or "").strip().lower()
    code = (data.get("code") or "").strip()
    password = data.get("password") or ""

    if not is_valid_email(email):
        return jsonify({"success": False, "message": "请输入有效的邮箱"}), 400
    if not _valid_code(code):
        return jsonify({"success": False, "message": "请输入6位数字验证码"}), 400
    ok, msg = validate_password(password)
    if not ok:
        return jsonify({"success": False, "message": msg}), 400

    user = db.user.get_user_by_email(email)
    if not user:
        return jsonify({"success": False, "message": "该邮箱未注册"}), 400

    code_info = db.verify.get_verify_code(email, code, "password_reset")
    if not code_info:
        db.verify.increment_verify_code_attempts(email, "password_reset")
        return jsonify({"success": False, "message": "验证码无效或已过期"}), 400

    ok, msg = db.user.reset_password(user["id"], password)
    if not ok:
        return jsonify({"success": False, "message": msg}), 400
    db.verify.mark_verify_code_used(email, code, "password_reset")
    _cleanup_codes(email, "password_reset")
    return jsonify({"success": True, "message": "密码重置成功"})
