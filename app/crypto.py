# -*- coding: utf-8 -*-
"""字符串混淆与本地凭证加解密。

纯标准库实现，不引入任何第三方加密依赖。

* :func:`reveal` / :func:`hide` —— 常量字符串的 XOR 混淆（防止后端地址被随意查看/修改）
* :func:`seal` / :func:`unseal`  —— 本地凭证文件（account.bin）的加解密（HMAC-SHA256 CTR + 鉴权标签）
"""

from __future__ import annotations

import hashlib
import hmac
import os
import platform
import uuid

# 混淆密钥（与生成字面量时使用的密钥保持一致）
_XOR_KEY = bytes([
    0x5a, 0x36, 0xc7, 0x11, 0x93, 0x4e, 0x08, 0xb2,
    0x6d, 0xf1, 0x3c, 0x85, 0x27, 0xda, 0x64, 0x19,
])

_MAGIC = b"CRF1"
_NONCE_LEN = 16
_TAG_LEN = 32


def _xor(data: bytes) -> bytes:
    n = len(_XOR_KEY)
    return bytes(b ^ _XOR_KEY[i % n] for i, b in enumerate(data))


def reveal(blob: bytes) -> str:
    """把混淆后的字节还原为明文。"""
    return _xor(bytes(blob)).decode("utf-8")


def hide(text: str) -> bytes:
    """把明文混淆为字节（生成字面量时使用）。"""
    return _xor(text.encode("utf-8"))


# ────────────────────────── 本地凭证 ──────────────────────────

_SALT = b"CrForum::local-store::v1"


def _machine_id() -> bytes:
    """机器相关指纹（不联网、不依赖额外库）。"""
    parts = [
        str(uuid.getnode()),
        platform.node(),
        os.environ.get("USERNAME") or os.environ.get("USER") or "",
        os.environ.get("USERPROFILE") or os.path.expanduser("~"),
    ]
    return "|".join(parts).encode("utf-8", "replace")


def derive_key(extra: bytes = b"", iterations: int = 120_000) -> bytes:
    """由机器指纹派生 32 字节密钥。"""
    return hashlib.pbkdf2_hmac(
        "sha256", _machine_id() + extra, _SALT, iterations, dklen=32
    )


def _keystream(key: bytes, length: int) -> bytes:
    out = bytearray()
    counter = 0
    while len(out) < length:
        out += hmac.new(key, counter.to_bytes(8, "big"), hashlib.sha256).digest()
        counter += 1
    return bytes(out[:length])


def seal(plain: bytes, *, key: bytes | None = None) -> bytes:
    """加密字节串，返回 ``CRF1 | nonce | ciphertext | tag``。"""
    if key is None:
        key = derive_key()
    nonce = os.urandom(_NONCE_LEN)
    stream = _keystream(key + nonce, len(plain))
    cipher = bytes(a ^ b for a, b in zip(plain, stream))
    tag = hmac.new(key, _MAGIC + nonce + cipher, hashlib.sha256).digest()
    return _MAGIC + nonce + cipher + tag


def unseal(blob: bytes, *, key: bytes | None = None) -> bytes:
    """解密 :func:`seal` 的产物；失败抛 :class:`ValueError`。"""
    if key is None:
        key = derive_key()
    if not isinstance(blob, (bytes, bytearray)):
        raise ValueError("密文类型错误")
    blob = bytes(blob)
    if not blob.startswith(_MAGIC) or len(blob) < 4 + _NONCE_LEN + _TAG_LEN:
        raise ValueError("密文格式错误")
    body = blob[4:]
    nonce, cipher, tag = (body[:_NONCE_LEN],
                          body[_NONCE_LEN:-_TAG_LEN],
                          body[-_TAG_LEN:])
    expect = hmac.new(key, _MAGIC + nonce + cipher, hashlib.sha256).digest()
    if not hmac.compare_digest(expect, tag):
        raise ValueError("密文校验失败")
    stream = _keystream(key + nonce, len(cipher))
    return bytes(a ^ b for a, b in zip(cipher, stream))


# ────────────────────────── 小工具 ──────────────────────────


def md5_hex(text: str) -> str:
    return hashlib.md5(text.encode("utf-8")).hexdigest()


def sha256_hex(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def random_token(length: int = 16) -> str:
    """随机 hex 串（用于文件名等）。"""
    return os.urandom((length + 1) // 2).hex()[:length]
