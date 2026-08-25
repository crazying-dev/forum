"""用户相关数据库操作。"""
import random
import uuid
import time
from typing import Optional, Union

import psycopg2

import config
from db import execute_query, execute_insert
from api.encrypt import verify_password, hash_password


def _gen_id(prefix: Optional[str] = None) -> str:
    """生成短 ID：前缀 + 16 位 UUID hex 截断。"""
    p = prefix or config.USER_ID_PREFIX
    # 仅允许白名单前缀（HG / YJ / RL），非法前缀回落默认
    if p not in config.ALLOWED_USER_PREFIXES:
        p = config.USER_ID_PREFIX
    return f"{p}{uuid.uuid4().hex[:16].upper()}"


def _row_to_user(row: Optional[dict]) -> Optional[dict]:
    """把 SELECT 行转成对外 dict（统一键名）。"""
    if not row:
        return None
    return {
        "id": row.get("id"),
        "name": row.get("name"),
        "avatar": row.get("avatar"),
        "email": row.get("email"),
        "password": row.get("password"),    # 保留哈希供 Token 校验
        "gender": row.get("gender", 0),
        "age": row.get("age") or "",
        "intro": row.get("intro") or "",
        "vip": row.get("vip") or "0",
        "prefix": row.get("prefix") or "",
        "is_banned": row.get("is_banned", 0),
        "email_verified": row.get("email_verified", 0),
        "created_at": str(row["created_at"]) if row.get("created_at") else None,
        "last_login": str(row["last_login"]) if row.get("last_login") else None,
    }


# ──────────────────────────────────────────────
# 查询
# ──────────────────────────────────────────────
def get_user_by_id(user_id: str) -> Optional[dict]:
    if not user_id:
        return None
    row = execute_query(
        "SELECT * FROM users WHERE id = %s",
        (user_id,), fetch=True,
    )
    return _row_to_user(row)


def get_user_by_name(name: str) -> Optional[dict]:
    if not name:
        return None
    row = execute_query(
        "SELECT * FROM users WHERE name = %s",
        (name.strip(),), fetch=True,
    )
    return _row_to_user(row)


def get_user_by_email(email: str) -> Optional[dict]:
    if not email:
        return None
    row = execute_query(
        "SELECT * FROM users WHERE email = %s",
        (email.strip(),), fetch=True,
    )
    return _row_to_user(row)


def get_user_by_login_identifier(identifier: str) -> Optional[dict]:
    """identifier 可以是用户名或邮箱，自动识别。"""
    if not identifier:
        return None
    s = identifier.strip()
    if "@" in s:
        return get_user_by_email(s)
    return get_user_by_name(s)


# ──────────────────────────────────────────────
# 注册
# ──────────────────────────────────────────────
def create_user(name: str, email: str, raw_password: str) -> dict:
    """创建新用户。

    Returns:
        {"success": True, "id": ..., "avatar": ...} 或
        {"success": False, "error": ..., "message": ...}
    """
    user_id = _gen_id(config.USER_ID_PREFIX)
    avatar = random.choice(config.DEFAULT_AVATARS)
    hashed = hash_password(raw_password)
    try:
        execute_insert(
            "INSERT INTO users (id, name, avatar, email, password, vip)"
            " VALUES (%s, %s, %s, %s, %s, %s)",
            (user_id, name, avatar, email, hashed, config.vip),
        )
        return {"success": True, "id": user_id, "avatar": avatar}
    except psycopg2.IntegrityError as e:
        msg = str(e).lower()
        if "email" in msg:
            return {"success": False, "error": "email_exists", "message": "邮箱已被注册"}
        if "name" in msg:
            return {"success": False, "error": "name_exists", "message": "用户名已被占用"}
        return {"success": False, "error": "integrity_error", "message": f"数据冲突: {e}"}
    except Exception as e:
        return {"success": False, "error": "db_error", "message": f"数据库错误: {e}"}


# ──────────────────────────────────────────────
# 登录（密码验证 + 更新 last_login）
# ──────────────────────────────────────────────
def LoginINFOTrueorFlase(username_or_email: str, raw_password: str, client_ip: Optional[str] = None) -> Union[
	dict, bool]:
    """与原调用签名兼容的登录验证函数。

    Returns:
        成功 → 用户 dict（含 password 哈希供上层生成 token）
        失败 → False
    """
    user = get_user_by_login_identifier(username_or_email)
    if not user:
        return False
    if user.get("is_banned"):
        return False
    if not verify_password(raw_password, user.get("password") or ""):
        return False
    # 更新最后登录时间
    try:
        execute_query(
            "UPDATE users SET last_login = CURRENT_TIMESTAMP WHERE id = %s",
            (user["id"],),
        )
    except Exception:
        pass
    return user


# ──────────────────────────────────────────────
# 更新用户信息
# ──────────────────────────────────────────────
_ALLOWED_UPDATE_FIELDS = {"avatar", "gender", "age", "intro", "name", "prefix"}


def update_user(user_id: str, **fields) -> tuple[bool, str]:
    """按字段更新用户信息。

    Args:
        user_id: 目标用户 ID
        **fields: avatar/gender/age/intro/name/prefix

    Returns:
        (ok, message)
    """
    if not user_id:
        return False, "缺少用户ID"
    updates = {k: v for k, v in fields.items() if k in _ALLOWED_UPDATE_FIELDS}
    if not updates:
        return False, "没有要更新的字段"

    # name 唯一性校验
    if "name" in updates:
        existing = get_user_by_name(updates["name"])
        if existing and existing["id"] != user_id:
            return False, "用户名已被占用"

    cols = ", ".join(f"{k} = %s" for k in updates.keys())
    params = list(updates.values()) + [user_id]
    try:
        rowcount = execute_query(f"UPDATE users SET {cols} WHERE id = %s", tuple(params))
        if rowcount and rowcount > 0:
            return True, "更新成功"
        return False, "未找到对应用户"
    except psycopg2.IntegrityError as e:
        return False, f"数据冲突: {e}"
    except Exception as e:
        return False, f"数据库错误: {e}"


# ──────────────────────────────────────────────
# 改密码
# ──────────────────────────────────────────────
def change_password(user_id: str, old_raw: str, new_raw: str) -> tuple[bool, str]:
    """修改密码：需校验旧密码。"""
    user = get_user_by_id(user_id)
    if not user:
        return False, "用户不存在"
    if not verify_password(old_raw, user["password"] or ""):
        return False, "原密码错误"
    try:
        rowcount = execute_query(
            "UPDATE users SET password = %s WHERE id = %s",
            (hash_password(new_raw), user_id),
        )
        if rowcount and rowcount > 0:
            return True, "密码修改成功"
        return False, "未找到对应用户"
    except Exception as e:
        return False, f"数据库错误: {e}"


def reset_password(user_id: str, new_raw: str) -> tuple[bool, str]:
    """重置密码（无需旧密码，供找回密码功能使用）。"""
    user = get_user_by_id(user_id)
    if not user:
        return False, "用户不存在"
    try:
        rowcount = execute_query(
            "UPDATE users SET password = %s WHERE id = %s",
            (hash_password(new_raw), user_id),
        )
        if rowcount and rowcount > 0:
            return True, "密码重置成功"
        return False, "未找到对应用户"
    except Exception as e:
        return False, f"数据库错误: {e}"
