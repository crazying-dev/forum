"""邮箱验证 token 数据访问。"""
import time
import uuid

from db import execute_query, execute_insert


def create_verify_token(user_id, token_type, expires_minutes=30):
    """创建验证 token（email_verify / password_reset）。"""
    token = str(uuid.uuid4())
    expires_at = time.strftime(
        "%Y-%m-%d %H:%M:%S", time.localtime(time.time() + expires_minutes * 60)
    )
    try:
        execute_insert(
            "INSERT INTO verify_tokens (user_id, token, token_type, expires_at) VALUES (%s, %s, %s, %s)",
            (user_id, token, token_type, expires_at),
        )
        return {"success": True, "token": token}
    except Exception as e:
        return {"success": False, "error": f"生成验证链接失败: {e}"}


def get_verify_token(token, token_type):
    """获取未过期的验证 token，不存在返回 None。"""
    row = execute_query(
        "SELECT user_id, token, token_type, expires_at FROM verify_tokens "
        "WHERE token = %s AND token_type = %s AND expires_at > CURRENT_TIMESTAMP",
        (token, token_type),
        fetch=True,
    )
    if not row:
        return None
    return {
        "user_id": row.get("user_id"),
        "token": row.get("token"),
        "token_type": row.get("token_type"),
        "expires_at": str(row.get("expires_at")) if row.get("expires_at") else None,
    }


def delete_verify_token(token):
    execute_query("DELETE FROM verify_tokens WHERE token = %s", (token,))


def update_user_email_verified(user_id):
    execute_query("UPDATE users SET email_verified = 1 WHERE id = %s", (user_id,))


# ──────────────────────────────────────────────
# 6 位数字验证码（注册 / 邮箱验证 / 验证码重置密码）
# 表 verify_codes 已由 config.CREATE_VERIFY_CODES_TABLE_SQL 建好
# ──────────────────────────────────────────────
def create_verify_code(email, code, purpose, expires_minutes=5):
    """生成一条验证码记录（email + code + purpose）。"""
    expires_at = time.strftime(
        "%Y-%m-%d %H:%M:%S", time.localtime(time.time() + expires_minutes * 60)
    )
    try:
        execute_insert(
            "INSERT INTO verify_codes (email, code, purpose, expires_at) VALUES (%s, %s, %s, %s)",
            (email, code, purpose, expires_at),
        )
        return {"success": True}
    except Exception as e:
        return {"success": False, "error": f"生成验证码失败: {e}"}


def get_verify_code(email, code, purpose):
    """获取未使用且未过期的验证码记录，不存在返回 None。"""
    return execute_query(
        "SELECT id, email, code, purpose, attempts FROM verify_codes "
        "WHERE email = %s AND code = %s AND purpose = %s AND used = 0 "
        "AND expires_at > CURRENT_TIMESTAMP ORDER BY id DESC LIMIT 1",
        (email, code, purpose),
        fetch=True,
    )


def increment_verify_code_attempts(email, purpose):
    execute_query(
        "UPDATE verify_codes SET attempts = attempts + 1 WHERE email = %s AND purpose = %s",
        (email, purpose),
    )


def mark_verify_code_used(email, code, purpose):
    execute_query(
        "UPDATE verify_codes SET used = 1 WHERE email = %s AND code = %s AND purpose = %s",
        (email, code, purpose),
    )
