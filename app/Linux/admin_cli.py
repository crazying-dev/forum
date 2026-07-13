#!/usr/bin/env python3
import sys
import os
import json

APP_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, APP_DIR)

CONFIG_FILE = os.path.join(APP_DIR, "config.bin")


def decrypt_config(data):
    return ''.join([chr((b - 1) % 256) for b in data])


def load_config():
    if not os.path.exists(CONFIG_FILE):
        print(f"[错误] 未找到配置文件: {CONFIG_FILE}")
        return None
    try:
        with open(CONFIG_FILE, "rb") as f:
            encrypted = f.read()
        decrypted = decrypt_config(encrypted)
        return json.loads(decrypted)
    except Exception as e:
        print(f"[错误] 配置文件解密失败: {e}")
        return None


def print_banner():
    print("=" * 50)
    print("  妖精论坛管理控制台 - 命令行版")
    print("=" * 50)


def print_main_menu():
    print("\n主菜单:")
    print("  1. 用户管理")
    print("  2. 帖子管理")
    print("  3. 统计信息")
    print("  0. 退出")


def confirm(prompt):
    return input(f"{prompt} [y/N]: ").strip().lower() == 'y'


def main():
    config = load_config()
    if not config:
        print("\n请运行 encrypt_config.py 生成配置文件后再使用。")
        sys.exit(1)

    base_url = config.get('apiUrl', 'admin.forum.crazying-dev.top')
    admin_id = config.get('adminId')
    admin_token = config.get('adminToken')

    if not admin_id or not admin_token:
        print("[错误] 配置文件缺少 adminId 或 adminToken")
        sys.exit(1)

    try:
        from api_client import AdminAPIClient
        from user_manager import UserManager
        from post_manager import PostManager
    except ImportError as e:
        print(f"\n[错误] 加载模块失败: {e}")
        sys.exit(1)

    api_client = AdminAPIClient(base_url, admin_id, admin_token)
    user_mgr = UserManager(api_client)
    post_mgr = PostManager(api_client)

    print_banner()
    print(f"API地址: {base_url}")
    print(f"管理员ID: {admin_id}")
    print(f"管理员令牌: {'*' * len(admin_token)}")

    while True:
        print_main_menu()
        choice = input("\n选择: ").strip()

        if choice == "1":
            user_mgr.run()
        elif choice == "2":
            post_mgr.run()
        elif choice == "3":
            stats = post_mgr.get_stats()
            if stats:
                print("\n" + "=" * 40)
                print("  论坛统计信息")
                print("=" * 40)
                print(f"  总用户数:     {stats['users']}")
                print(f"  帖子总数:     {stats['posts']}")
                print(f"  评论总数:     {stats['comments']}")
                print(f"  待处理举报:   {stats['pending_reports']}")
                print(f"  已封禁用户:   {stats['banned_users']}")
                print("=" * 40)
        elif choice == "0":
            print("\n[退出] 再见")
            break
        else:
            print("[错误] 无效选择")


if __name__ == "__main__":
    if len(sys.argv) >= 2:
        config = load_config()
        if not config:
            sys.exit(1)

        base_url = config.get('apiUrl', 'admin.forum.crazying-dev.top')
        admin_id = config.get('adminId')
        admin_token = config.get('adminToken')

        if not admin_id or not admin_token:
            print("[错误] 配置文件缺少 adminId 或 adminToken")
            sys.exit(1)

        try:
            from api_client import AdminAPIClient
            from user_manager import UserManager
            from post_manager import PostManager
        except ImportError as e:
            print(f"[错误] 加载模块失败: {e}")
            sys.exit(1)

        api_client = AdminAPIClient(base_url, admin_id, admin_token)
        user_mgr = UserManager(api_client)
        post_mgr = PostManager(api_client)

        cmd = sys.argv[1]

        if cmd == "users":
            user_mgr.list_users()
        elif cmd == "search" and len(sys.argv) >= 3:
            user_mgr.search_user(sys.argv[2])
        elif cmd == "ban" and len(sys.argv) >= 3:
            user_mgr.ban_user(sys.argv[2])
        elif cmd == "unban" and len(sys.argv) >= 3:
            user_mgr.unban_user(sys.argv[2])
        elif cmd == "reports":
            post_mgr.list_reports()
        elif cmd == "post" and len(sys.argv) >= 3:
            post_mgr.show_post(sys.argv[2])
        elif cmd == "delete-post" and len(sys.argv) >= 3:
            post_mgr.delete_post(sys.argv[2])
        elif cmd == "delete-comment" and len(sys.argv) >= 3:
            post_mgr.delete_comment(sys.argv[2])
        elif cmd == "stats":
            stats = post_mgr.get_stats()
            if stats:
                print("\n" + "=" * 40)
                print("  论坛统计信息")
                print("=" * 40)
                print(f"  总用户数:     {stats['users']}")
                print(f"  帖子总数:     {stats['posts']}")
                print(f"  评论总数:     {stats['comments']}")
                print(f"  待处理举报:   {stats['pending_reports']}")
                print(f"  已封禁用户:   {stats['banned_users']}")
                print("=" * 40)
        else:
            print(f"[错误] 未知命令: {cmd}")
    else:
        main()