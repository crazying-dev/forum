"""
加密工具模块 - AES-GCM 请求/响应参数加密
使用 AUTH_SALT 派生 AES-256 密钥，实现双向加密通信
"""
import json
import base64
import os
from typing import Any, Dict

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes

from api.config import AUTH_SALT


# 固定盐值，确保密钥派生确定性（同一 AUTH_SALT 始终产生同一密钥）
_KEY_DERIVATION_SALT = b'forum_key_v1'
_KEY_ITERATIONS = 100000
_KEY_LENGTH = 32  # 256 位


def _derive_key() -> bytes:
    """从 AUTH_SALT 派生 256 位 AES 密钥（PBKDF2HMAC + SHA256，确定性派生）"""
    if not AUTH_SALT:
        raise ValueError("AUTH_SALT 未配置，无法派生加密密钥")
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=_KEY_LENGTH,
        salt=_KEY_DERIVATION_SALT,
        iterations=_KEY_ITERATIONS,
    )
    key = kdf.derive(AUTH_SALT.encode('utf-8'))
    return key


def _encrypt(plaintext: str) -> str:
    """内部：将明文字符串加密为 base64(nonce + ciphertext + tag)"""
    key = _derive_key()
    aesgcm = AESGCM(key)
    nonce = os.urandom(12)  # 96 位 nonce，AES-GCM 推荐长度
    ciphertext = aesgcm.encrypt(nonce, plaintext.encode('utf-8'), None)
    # ciphertext 已包含认证标签（后 16 字节）
    encrypted_bytes = nonce + ciphertext
    return base64.b64encode(encrypted_bytes).decode('utf-8')


def _decrypt(encrypted: str) -> str:
    """内部：将 base64(nonce + ciphertext + tag) 解密为明文字符串"""
    try:
        key = _derive_key()
        encrypted_bytes = base64.b64decode(encrypted)
        if len(encrypted_bytes) < 13:  # nonce(12) + 最小 tag(1)
            raise ValueError("密文数据长度不足，格式无效")
        nonce = encrypted_bytes[:12]
        ciphertext = encrypted_bytes[12:]
        aesgcm = AESGCM(key)
        plaintext = aesgcm.decrypt(nonce, ciphertext, None)
        return plaintext.decode('utf-8')
    except (base64.binascii.Error, ValueError, IndexError) as e:
        raise ValueError(f"密文解码失败: {e}")
    except Exception as e:
        raise ValueError(f"解密失败，数据可能被篡改或密钥不匹配: {e}")


def encrypt_request(data: Dict[str, Any]) -> str:
    """加密请求参数（dict → base64 密文）

    Args:
        data: 要加密的请求字典

    Returns:
        Base64 编码的密文字符串

    Raises:
        ValueError: 当序列化或加密失败时抛出
    """
    if not isinstance(data, dict):
        raise TypeError(f"encrypt_request 要求 dict 类型，收到 {type(data).__name__}")
    try:
        plaintext = json.dumps(data, ensure_ascii=False, separators=(',', ':'))
        return _encrypt(plaintext)
    except (TypeError, ValueError) as e:
        raise ValueError(f"请求数据序列化失败: {e}")


def decrypt_request(encrypted: str) -> Dict[str, Any]:
    """解密请求参数（base64 密文 → dict）

    Args:
        encrypted: Base64 编码的密文字符串

    Returns:
        解密后的字典

    Raises:
        ValueError: 当解密或 JSON 解析失败时抛出
    """
    if not isinstance(encrypted, str) or not encrypted.strip():
        raise ValueError("解密输入必须是非空字符串")
    try:
        plaintext = _decrypt(encrypted)
        data = json.loads(plaintext)
        if not isinstance(data, dict):
            raise ValueError(f"解密后的数据不是 dict 类型，实际为 {type(data).__name__}")
        return data
    except json.JSONDecodeError as e:
        raise ValueError(f"解密数据 JSON 解析失败: {e}")


def encrypt_response(data: Any) -> str:
    """加密响应数据

    与 encrypt_request 实现相同，仅命名不同以体现语义差异。

    Args:
        data: 任意可 JSON 序列化的数据

    Returns:
        Base64 编码的密文字符串

    Raises:
        ValueError: 当序列化或加密失败时抛出
    """
    try:
        plaintext = json.dumps(data, ensure_ascii=False, separators=(',', ':'))
        return _encrypt(plaintext)
    except (TypeError, ValueError) as e:
        raise ValueError(f"响应数据序列化失败: {e}")


def decrypt_response(encrypted: str) -> Any:
    """解密响应数据

    与 decrypt_request 实现相同，仅命名不同以体现语义差异。
    不强制要求返回 dict 类型，以支持任意 JSON 数据类型。

    Args:
        encrypted: Base64 编码的密文字符串

    Returns:
        解密后的数据（任意 JSON 类型）

    Raises:
        ValueError: 当解密或 JSON 解析失败时抛出
    """
    if not isinstance(encrypted, str) or not encrypted.strip():
        raise ValueError("解密输入必须是非空字符串")
    try:
        plaintext = _decrypt(encrypted)
        return json.loads(plaintext)
    except json.JSONDecodeError as e:
        raise ValueError(f"解密数据 JSON 解析失败: {e}")


# Flask 辅助函数
def encrypted_api_response(success: bool, data: Any = None, message: str = ""):
    """返回加密的 API 响应（Flask jsonify）

    构建包含 success/data/message 的响应字典，加密后以 {encrypted: ...} 格式返回。

    Args:
        success: 操作是否成功
        data: 负载数据（可选，可 JSON 序列化）
        message: 提示消息（可选）

    Returns:
        Flask Response 对象，包含加密后的 JSON 数据
    """
    from flask import jsonify
    payload: Dict[str, Any] = {"success": success}
    if data is not None:
        payload["data"] = data
    if message:
        payload["message"] = message
    encrypted_data = encrypt_response(payload)
    return jsonify({"encrypted": encrypted_data})


# ── 路由装饰器 ────────────────────────────────────────────

def encrypted_endpoint(f):
    """路由装饰器：自动解密请求体并加密响应。

    用法:
        @app.route('/api/secret/data', methods=['POST'])
        @encrypted_endpoint
        def my_secret_route(decrypted_data):
            # decrypted_data 是解密后的请求参数（dict）
            return {'some': 'response_data'}

    请求格式: {"encrypted": "<base64密文>"}
    响应格式: {"encrypted": "<base64密文>"}
    """
    import functools
    from flask import request, jsonify

    @functools.wraps(f)
    def wrapper(*args, **kwargs):
        try:
            body = request.get_json(silent=True) or {}
            encrypted = body.get('encrypted')
            if not encrypted:
                return jsonify({'success': False, 'message': '请求体缺少 encrypted 字段'}), 400
            decrypted_data = decrypt_request(encrypted)
        except (ValueError, TypeError) as e:
            return jsonify({'success': False, 'message': f'解密失败: {e}'}), 400
        except Exception as e:
            return jsonify({'success': False, 'message': '请求解密异常'}), 500

        try:
            result = f(decrypted_data, *args, **kwargs)
        except Exception as e:
            return jsonify({'success': False, 'message': f'处理请求时出错: {e}'}), 500

        try:
            encrypted_result = encrypt_response(result)
            return jsonify({'encrypted': encrypted_result})
        except (ValueError, TypeError) as e:
            return jsonify({'success': False, 'message': f'响应加密失败: {e}'}), 500

    return wrapper


def require_encryption(f):
    """路由装饰器：仅解密请求，响应保持明文。

    用法:
        @app.route('/api/secret/action', methods=['POST'])
        @require_encryption
        def my_action(decrypted_data):
            # decrypted_data 是解密后的请求参数（dict）
            return jsonify({'success': True})

    请求格式: {"encrypted": "<base64密文>"}
    """
    import functools
    from flask import request, jsonify

    @functools.wraps(f)
    def wrapper(*args, **kwargs):
        try:
            body = request.get_json(silent=True) or {}
            encrypted = body.get('encrypted')
            if not encrypted:
                return jsonify({'success': False, 'message': '请求体缺少 encrypted 字段'}), 400
            decrypted_data = decrypt_request(encrypted)
        except (ValueError, TypeError) as e:
            return jsonify({'success': False, 'message': f'解密失败: {e}'}), 400
        except Exception as e:
            return jsonify({'success': False, 'message': '请求解密异常'}), 500

        return f(decrypted_data, *args, **kwargs)

    return wrapper
