"""Cloudflare Turnstile 人机验证（服务端 siteverify 校验）。

为什么校验必须放服务端
----------------------
Cloudflare 规定 Siteverify 只能在后端调用；token 最长 2048 字符、有效期 300 秒、
**一次性**（校验一次即作废），因此一次业务请求对应一个 token。

接口契约（与自研滑块共用字段：接口零改动的关键）
------------------------------------------------
客户端把 Turnstile token 放进 **``captcha_token``** 字段提交业务请求，
所以 ``@captcha_required`` 与 11 个受保护接口（api/user、api/email）一行都不用改。

配置（.env / 环境变量）
-----------------------
    CAPTCHA_PROVIDER=turnstile
    TURNSTILE_SITEKEY=<Dashboard 里的 Site Key>
    TURNSTILE_SECRET=<Dashboard 里的 Secret Key>
可选：
    TURNSTILE_VERIFY_URL        默认 https://challenges.cloudflare.com/turnstile/v0/siteverify
    TURNSTILE_TIMEOUT           默认 10 秒
    TURNSTILE_EXPECTED_HOSTNAME 默认空（不校验）；填 www.yjlt.top 可进一步收紧

官方测试密钥（联调用；配置真实密钥后自然不再使用）
    Site Key    1x00000000000000000000AA
    Secret Key  1x0000000000000000000000000000000AA
"""
from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request

import config

# 与自研滑块共用的请求体字段名（接口零改动的关键）
TOKEN_FIELD = "captcha_token"

# Cloudflare 官方测试密钥
TEST_SITEKEY = "1x00000000000000000000AA"
TEST_SECRET = "1x0000000000000000000000000000000AA"

DEFAULT_VERIFY_URL = "https://challenges.cloudflare.com/turnstile/v0/siteverify"

# siteverify 的 error-codes → 面向用户的中文文案
ERROR_MESSAGES = {
    "missing-input-secret": "人机验证服务配置有误，请联系管理员",
    "invalid-input-secret": "人机验证服务配置有误，请联系管理员",
    "internal-error": "人机验证服务暂时不可用，请稍后重试",
    "missing-input-response": "请先完成人机验证",
    "invalid-input-response": "人机验证失败，请重试",
    "bad-request": "人机验证失败，请重试",
    "timeout-or-duplicate": "人机验证已过期，请重新验证",
}
DEFAULT_ERROR_MESSAGE = "人机验证失败，请重试"


def sitekey() -> str:
    return str(getattr(config, "TURNSTILE_SITEKEY", "") or "").strip()


def secret() -> str:
    return str(getattr(config, "TURNSTILE_SECRET", "") or "").strip()


def configured() -> bool:
    """sitekey 与 secret 都齐全才算可用；缺任意一个由上层回退自研滑块。"""
    return bool(sitekey() and secret())


def verify_url() -> str:
    url = str(getattr(config, "TURNSTILE_VERIFY_URL", "") or "").strip()
    return url or DEFAULT_VERIFY_URL


def timeout() -> int:
    try:
        value = int(getattr(config, "TURNSTILE_TIMEOUT", 10))
    except (TypeError, ValueError):
        value = 10
    return value if value > 0 else 10


def expected_hostname() -> str:
    return str(getattr(config, "TURNSTILE_EXPECTED_HOSTNAME", "") or "").strip().lower()


def message_for(codes) -> str:
    """error-codes → 中文文案（纯函数，便于单测）。"""
    if isinstance(codes, str):
        codes = [codes]
    for code in (codes or []):
        text = ERROR_MESSAGES.get(str(code))
        if text:
            return text
    return DEFAULT_ERROR_MESSAGE


def request_payload(token: str, remote_ip: str = "") -> dict:
    """构造 siteverify 请求体（secret 只出现在服务端）。"""
    data = {"secret": secret(), "response": token}
    if remote_ip:
        data["remoteip"] = remote_ip
    return data


def _post_siteverify(data: dict) -> dict:
    """表单 POST 到 siteverify 并解析 JSON；网络异常时抛出，由调用方兜底。"""
    body = urllib.parse.urlencode(data).encode("utf-8")
    req = urllib.request.Request(
        verify_url(),
        data=body,
        headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout()) as resp:  # noqa: S310 — URL 来自配置
        raw = resp.read().decode("utf-8", "replace")
    return json.loads(raw or "{}")


def verify_token(token: str, remote_ip: str = "") -> tuple[bool, str]:
    """校验一个 Turnstile token，返回 (ok, message)。

    token 一次性：校验成功后再拿同一个 token 提交业务请求必定失败
    （Cloudflare 返回 ``timeout-or-duplicate``），这是预期行为。
    """
    token = (token or "").strip()
    if not token:
        return False, "请先完成人机验证"
    if not configured():
        return False, "人机验证服务配置有误，请联系管理员"
    try:
        result = _post_siteverify(request_payload(token, remote_ip))
    except urllib.error.HTTPError as e:
        print(f"[turnstile] siteverify HTTP {e.code}")
        return False, "人机验证服务暂时不可用，请稍后重试"
    except Exception as e:  # noqa: BLE001 — 网络 / 解析异常一律按失败处理
        print(f"[turnstile] siteverify 请求失败：{type(e).__name__}")
        return False, "人机验证服务暂时不可用，请稍后重试"
    if not isinstance(result, dict) or not result.get("success"):
        codes = result.get("error-codes") if isinstance(result, dict) else None
        return False, message_for(codes)
    expected = expected_hostname()
    got = str(result.get("hostname") or "").strip().lower()
    if expected and got != expected:
        return False, "人机验证失败，请重试"
    return True, ""


__all__ = [
    "TOKEN_FIELD",
    "TEST_SITEKEY",
    "TEST_SECRET",
    "DEFAULT_VERIFY_URL",
    "ERROR_MESSAGES",
    "sitekey",
    "secret",
    "configured",
    "verify_url",
    "timeout",
    "expected_hostname",
    "message_for",
    "request_payload",
    "verify_token",
]
