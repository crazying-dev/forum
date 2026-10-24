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
        "title": row.get("title") or "",
        "is_banned": row.get("is_banned", 0),
        "email_verified": row.get("email_verified", 0),
        "deleted_at": str(row["deleted_at"]) if row.get("deleted_at") else None,
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
def _auto_follow_default(user_id: str) -> None:
    """新用户创建后自动关注官方账号 config.DEFAULT_FOLLOW_USER_ID。

    尽力而为：目标账号不存在、已关注或插入冲突时静默跳过，绝不影响注册主流程。
    """
    target = (getattr(config, "DEFAULT_FOLLOW_USER_ID", "") or "").strip()
    if not target or target == user_id:
        return
    try:
        execute_insert(
            "INSERT INTO user_follows (follower_id, following_id) VALUES (%s, %s)"
            " ON CONFLICT (follower_id, following_id) DO NOTHING",
            (user_id, target),
        )
    except Exception as e:
        print(f"[warn] 新用户 {user_id} 自动关注 {target} 失败: {e}")


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
        # 新用户默认关注官方账号（失败不影响注册）
        _auto_follow_default(user_id)
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
    # 已注销账号（匿名化保留）不可再登录
    if user.get("deleted_at"):
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
_ALLOWED_UPDATE_FIELDS = {"avatar", "gender", "age", "intro", "name"}


def update_user(user_id: str, **fields) -> tuple[bool, str]:
    """按字段更新用户信息。

    Args:
        user_id: 目标用户 ID
        **fields: avatar/gender/age/intro/name

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


def change_email(user_id: str, new_email: str) -> tuple[bool, str]:
    """更换绑定邮箱（仅供「新邮箱验证码」校验通过后调用）。

    换绑成功后新邮箱天然已验证，故同时置 email_verified = 1。
    """
    if not user_id or not new_email:
        return False, "缺少参数"
    try:
        rowcount = execute_query(
            "UPDATE users SET email = %s, email_verified = 1 WHERE id = %s",
            (new_email.strip(), user_id),
        )
        if rowcount and rowcount > 0:
            return True, "邮箱已更换"
        return False, "未找到对应用户"
    except psycopg2.IntegrityError:
        return False, "该邮箱已被其他账号绑定"
    except Exception as e:
        return False, f"数据库错误: {e}"


def purge_user(user_id: str) -> dict:
    """彻底删除账号及其全部内容（不可恢复）。

    对应隐私政策「注销账号 → 彻底删除」：账号、帖子、评论、点赞、收藏、
    关注关系、举报记录、Bug 反馈、验证 token / 验证码全部清除。

    Returns:
        {"success": True, "mode": "purge"} 或 {"success": False, "message": ...}
    """
    if not user_id:
        return {"success": False, "message": "缺少用户ID"}
    user = get_user_by_id(user_id)
    if not user:
        return {"success": False, "message": "用户不存在"}
    email = (user.get("email") or "").strip()
    try:
        # 顺序：先清子表（含间接子表），再清评论/帖子，最后清用户
        execute_query("DELETE FROM comment_reports WHERE reporter_id = %s", (user_id,))
        execute_query(
            "DELETE FROM comment_reports WHERE comment_id IN "
            "(SELECT id FROM comments WHERE user_id = %s "
            " OR post_id IN (SELECT id FROM posts WHERE user_id = %s))",
            (user_id, user_id),
        )
        execute_query(
            "DELETE FROM comment_likes WHERE user_id = %s OR comment_id IN "
            "(SELECT id FROM comments WHERE user_id = %s "
            " OR post_id IN (SELECT id FROM posts WHERE user_id = %s))",
            (user_id, user_id, user_id),
        )
        execute_query("DELETE FROM post_reports WHERE reporter_id = %s", (user_id,))
        execute_query(
            "DELETE FROM post_reports WHERE post_id IN "
            "(SELECT id FROM posts WHERE user_id = %s)",
            (user_id,),
        )
        execute_query(
            "DELETE FROM post_likes WHERE user_id = %s OR post_id IN "
            "(SELECT id FROM posts WHERE user_id = %s)",
            (user_id, user_id),
        )
        execute_query(
            "DELETE FROM post_favorites WHERE user_id = %s OR post_id IN "
            "(SELECT id FROM posts WHERE user_id = %s)",
            (user_id, user_id),
        )
        execute_query(
            "DELETE FROM user_follows WHERE follower_id = %s OR following_id = %s",
            (user_id, user_id),
        )
        execute_query("DELETE FROM verify_tokens WHERE user_id = %s", (user_id,))
        # 本人发表的评论（其对他人评论的回复随 parent_id 级联移除）
        execute_query("DELETE FROM comments WHERE user_id = %s", (user_id,))
        # 本人帖子下的全部评论
        execute_query(
            "DELETE FROM comments WHERE post_id IN "
            "(SELECT id FROM posts WHERE user_id = %s)",
            (user_id,),
        )
        execute_query("DELETE FROM world WHERE sender_id = %s", (user_id,))
        # Bug 反馈里含 user_agent / page_url，属个人信息，一并删除
        execute_query("DELETE FROM bug_reports WHERE reporter_id = %s", (user_id,))
        if email:
            execute_query("DELETE FROM verify_codes WHERE email = %s", (email,))
        execute_query("DELETE FROM posts WHERE user_id = %s", (user_id,))
        execute_query("DELETE FROM users WHERE id = %s", (user_id,))
        return {"success": True, "mode": "purge"}
    except Exception as e:
        return {"success": False, "message": f"数据库错误: {e}"}


def anonymize_user(user_id: str) -> dict:
    """匿名化注销：清空个人标识，保留历史内容（作者显示为「已注销用户」）。

    用户名改为 config.DELETED_USER_NAME（重名则追加 _<6 位随机>），
    邮箱改为不可投递的唯一占位地址，密码改为随机串（无法再登录），
    头像回落默认头像，性别/年龄/简介/头衔一并清空，并写入 deleted_at。

    Returns:
        {"success": True, "mode": "anonymize", "name": ...} 或 {"success": False, ...}
    """
    if not user_id:
        return {"success": False, "message": "缺少用户ID"}
    user = get_user_by_id(user_id)
    if not user:
        return {"success": False, "message": "用户不存在"}
    base = getattr(config, "DELETED_USER_NAME", "已注销用户")
    name = base
    if get_user_by_name(name):
        name = f"{base}_{uuid.uuid4().hex[:6].upper()}"
    domain = getattr(config, "DELETED_USER_EMAIL_DOMAIN", "deleted.invalid")
    placeholder_email = f"deleted+{user_id.lower()}@{domain}"
    old_email = (user.get("email") or "").strip()
    try:
        execute_query(
            "UPDATE users SET name = %s, email = %s, password = %s, avatar = %s,"
            " gender = 0, age = NULL, intro = '', title = '', email_verified = 0,"
            " deleted_at = CURRENT_TIMESTAMP WHERE id = %s",
            (name, placeholder_email, hash_password(uuid.uuid4().hex),
             random.choice(config.DEFAULT_AVATARS), user_id),
        )
        execute_query("DELETE FROM verify_tokens WHERE user_id = %s", (user_id,))
        if old_email:
            execute_query("DELETE FROM verify_codes WHERE email = %s", (old_email,))
        return {"success": True, "mode": "anonymize", "name": name}
    except Exception as e:
        return {"success": False, "message": f"数据库错误: {e}"}


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
