#!/usr/bin/env python3
import sys
import os
import json


def encrypt(text):
    return bytes([(ord(c) + 1) % 256 for c in text])


def decrypt(data):
    return ''.join([chr((b - 1) % 256) for b in data])


def main():
    if len(sys.argv) >= 5:
        target = sys.argv[1]
        api_url = sys.argv[2]
        admin_id = sys.argv[3]
        admin_token = sys.argv[4]
    else:
        target = input("目标目录 (Win/Linux/all): ").strip() or "all"
        api_url = input("API地址 (默认 admin.forum.crazying-dev.top): ").strip() or "admin.forum.crazying-dev.top"
        admin_id = input("管理员ID: ").strip()
        admin_token = input("管理员令牌: ").strip()

    content = json.dumps({
        "apiUrl": api_url,
        "adminId": admin_id,
        "adminToken": admin_token
    }, ensure_ascii=False)
    encrypted = encrypt(content)

    targets = []
    if target.lower() == "win" or target.lower() == "all":
        targets.append(os.path.join("app", "Win", "config.bin"))
    if target.lower() == "linux" or target.lower() == "all":
        targets.append(os.path.join("app", "Linux", "config.bin"))

    for config_file in targets:
        os.makedirs(os.path.dirname(config_file), exist_ok=True)
        with open(config_file, "wb") as f:
            f.write(encrypted)
        print(f"[成功] 配置已加密保存到 {config_file}")

    print(f"\n原始内容: {content}")


if __name__ == "__main__":
    main()