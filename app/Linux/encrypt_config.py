#!/usr/bin/env python3
import json
import os

APP_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE = os.path.join(APP_DIR, "config.bin")


def encrypt(data):
    return bytes([(ord(c) + 1) % 256 for c in data])


def main():
    api_url = input("API地址 (默认 admin.forum.crazying-dev.top): ").strip() or "admin.forum.crazying-dev.top"
    admin_id = input("管理员ID: ").strip()
    admin_token = input("管理员令牌: ").strip()

    config = {
        "apiUrl": api_url,
        "adminId": admin_id,
        "adminToken": admin_token
    }

    data = json.dumps(config)
    encrypted = encrypt(data)

    with open(CONFIG_FILE, "wb") as f:
        f.write(encrypted)

    print(f"\n[成功] 配置文件已保存到: {CONFIG_FILE}")
    print(f"配置内容: {data}")


if __name__ == "__main__":
    main()