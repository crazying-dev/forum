"""加密与认证相关工具。

按用户要求：token 生成沿用 forum-new 原有 GetToken 逻辑：
    raw_data = repr((user_id, password, client_ip)).encode("utf-8")
    digest   = md5(raw_data).hexdigest()
    sig      = hmac_sha256(SECRET_KEY, raw_data).hexdigest()
    token    = f"{digest}.{sig}"
接口返回：f"token---{token}---{send_time}"
Cookie 只包含 token 与 ID。
"""
import hashlib
import hmac
import re
import time
from werkzeug.security import generate_password_hash, check_password_hash
import os

# ── HMAC 密钥：优先读 .env SECRET_KEY，兜底为原有 TestKeyFor1 ──
_SECRET_KEY_STR = os.getenv("SECRET_KEY", "TestKeyFor1")
SECRET_KEY = _SECRET_KEY_STR.encode("utf-8") if isinstance(_SECRET_KEY_STR, str) else b"TestKeyFor1"


# ──────────────────────────────────────────────
# 密码哈希（werkzeug pbkdf2:sha256）
# ──────────────────────────────────────────────
def hash_password(raw_password: str) -> str:
    return generate_password_hash(raw_password)


def verify_password(raw_password: str, hashed_password: str) -> bool:
    if not raw_password or not hashed_password:
        return False
    try:
        return check_password_hash(hashed_password, raw_password)
    except Exception:
        return False


# ──────────────────────────────────────────────
# 登录 Token（与原 tool/GetToken.py 算法一致）
# ──────────────────────────────────────────────
def GetToken(*args) -> str:
    """与原有 GetToken 完全一致的算法。

    返回格式: md5hex.hmac_sha256hex
    """
    raw_data = repr(args).encode("utf-8")
    sig = hmac.new(SECRET_KEY, raw_data, hashlib.sha256).hexdigest()
    digest = hashlib.md5(raw_data).hexdigest()
    return f"{digest}.{sig}"


def generate_login_token(user_id: str, password_hash: str, client_ip: str | None = None) -> tuple[str, str, int]:
    """生成登录完整 Token 字符串与各部分。

    自 v1.1 起 token 不再绑定 client_ip，避免移动网络/WIFI 切换导致掉登录。

    Args:
        user_id:        用户 ID
        password_hash:  用户密码哈希（数据库存的那个，用于生成 token 绑定）
        client_ip:      保留参数为兼容旧调用，实际不参与 token 计算

    Returns:
        (full_token_for_cookie, core_token, send_time)
        - full_token_for_cookie: "token---{core}---{st}" （直接写 cookie）
        - core_token:           "{md5}.{sig}"
        - send_time:            秒级时间戳
    """
    st = int(time.time())
    # 不再把 client_ip 放进 repr，保证 IP 变化时 token 仍然有效
    core = GetToken(user_id, password_hash)
    full = f"token---{core}---{st}"
    return full, core, st


def verify_login_token(user_id: str, cookie_token: str, password_hash: str,
                       client_ip: str | None = None, ttl_seconds: int | None = 7 * 24 * 3600) -> bool:
    """校验 cookie 中保存的 token。

    Args:
        user_id:       用户 ID
        cookie_token:  Cookie 里的 token（完整格式：token---{core}---{st}）
        password_hash: 数据库密码哈希
        client_ip:     保留兼容参数，不参与校验
        ttl_seconds:   有效期秒数（默认 7 天），None 不校验时间

    Returns:
        校验通过返回 True
    """
    if not user_id or not cookie_token or not password_hash:
        return False
    parts = cookie_token.split("---")
    if len(parts) != 3 or parts[0] != "token":
        return False
    provided_core = parts[1]
    try:
        st = int(parts[2])
    except (ValueError, TypeError):
        return False
    # 1. TTL 检查
    if ttl_seconds is not None:
        if abs(int(time.time()) - st) > ttl_seconds:
            return False
    # 2. 核心 token 重算比对（不绑 IP，跨网络稳定）
    expected_core = GetToken(user_id, password_hash)
    return hmac.compare_digest(expected_core, provided_core)


# ──────────────────────────────────────────────
# 输入校验
# ──────────────────────────────────────────────
_EMAIL_RE = re.compile(r"^[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}$")


def is_valid_email(email: str) -> bool:
    return bool(email and _EMAIL_RE.match(str(email).strip()))


def validate_password(password: str) -> tuple[bool, str]:
    if not password:
        return False, "密码不能为空"
    if len(password) < 8:
        return False, "密码至少8位"
    if not re.search(r"[A-Za-z]", password):
        return False, "密码需包含字母"
    if not re.search(r"\d", password):
        return False, "密码需包含数字"
    return True, ""


def validate_username(name: str) -> tuple[bool, str]:
    if not name:
        return False, "用户名不能为空"
    n = name.strip()
    if len(n) < 2 or len(n) > 20:
        return False, "用户名需要2-20个字符"
    return True, ""
