#!/usr/bin/env python3
"""
配置文件解密工具（后移一位）

用法:
    python app/encrypt_config.py
"""

import sys
import os
import json

APP_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE = os.path.join(APP_DIR, "config.bin")


def decrypt(data):
    """后移一位解密"""
    return ''.join([chr((b - 1) % 256) for b in data])


def load_config():
    """加载配置文件"""
    if not os.path.exists(CONFIG_FILE):
        return None
    try:
        with open(CONFIG_FILE, "rb") as f:
            encrypted = f.read()
        decrypted = decrypt(encrypted)
        import json
        return json.loads(decrypted)
    except Exception:
        return None


def main():
    config = load_config()
    if config:
        print(f"解密内容:\n{json.dumps(config, ensure_ascii=False, indent=2)}")
    else:
        print(f"[错误] 文件不存在或解密失败: {CONFIG_FILE}")


if __name__ == "__main__":
    main()
