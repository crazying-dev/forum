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
