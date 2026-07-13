#!/usr/bin/env python3
import sys
import os

APP_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, APP_DIR)


def print_users(users):
    if not users:
        print("[信息] 没有找到用户")
        return
    print(f"\n共 {len(users)} 个用户")
    print("=" * 110)
    print(f"{'#':<5} {'用户ID':<22} {'用户名':<14} {'邮箱':<26} {'VIP':<5} {'封禁':<5} {'年龄':<6} {'最后登录'}")
    print("-" * 110)
    for i, u in enumerate(users, 1):
        banned = "是" if u.get('is_banned') == 1 else "否"
        print(f"{i:<5} {u['id']:<22} {u['name']:<14} {u['email']:<26} {str(u['vip']):<5} {banned:<5} {str(u['age']):<6} {u.get('last_login', '-')}")
    print("=" * 110)


def confirm(prompt):
    return input(f"{prompt} [y/N]: ").strip().lower() == 'y'


class UserManager:

    def __init__(self, api_client):
        self.api = api_client

    def list_users(self):
        users = self.api.list_users()
        print_users(users)

    def search_user(self, identifier):
        users = self.api.find_user_smart(identifier)
        print_users(users)

    def ban_user(self, identifier):
        users = self.api.find_user_smart(identifier)
        if not users:
            print("[信息] 未找到用户")
            return
        print_users(users)
        for u in users:
            if confirm(f"确认封禁用户 {u['name']} ({u['id']})?"):
                if self.api.ban_user(u['id']):
                    print(f"[成功] 已封禁: {u['name']}")
                else:
                    print(f"[失败] 封禁失败")

    def unban_user(self, identifier):
        users = self.api.find_user_smart(identifier)
        if not users:
            print("[信息] 未找到用户")
            return
        print_users(users)
        for u in users:
            if confirm(f"确认解封用户 {u['name']} ({u['id']})?"):
                if self.api.unban_user(u['id']):
                    print(f"[成功] 已解封: {u['name']}")
                else:
                    print(f"[失败] 解封失败")

    def edit_user(self):
        kw = input("输入用户ID或用户名: ").strip()
        users = self.api.find_user_smart(kw)
        if not users:
            print("[信息] 未找到用户")
            return
        print_users(users)
        try:
            idx = int(input("选择序号: ")) - 1
            if 0 <= idx < len(users):
                user = users[idx]
                key = input("修改字段 (name/avatar/email/gender/age/intro/vip/password/is_banned): ").strip()
                value = input("修改值: ")
                if confirm(f"确认将 {user['name']} 的 {key} 修改为: {value}?"):
                    if self.api.update_user(user['id'], key, value):
                        print("[成功] 用户数据已更新")
                    else:
                        print("[失败] 更新未生效")
        except ValueError:
            print("[错误] 输入无效")

    def run(self):
        while True:
            print("\n" + "=" * 50)
            print("  用户管理")
            print("=" * 50)
            print("\n菜单:")
            print("  1. 查看所有用户")
            print("  2. 搜索用户")
            print("  3. 修改用户信息")
            print("  4. 封禁用户")
            print("  5. 解封用户")
            print("  0. 返回")
            choice = input("\n选择: ").strip()

            if choice == "1":
                self.list_users()
            elif choice == "2":
                kw = input("输入用户ID或用户名: ").strip()
                self.search_user(kw)
            elif choice == "3":
                self.edit_user()
            elif choice == "4":
                kw = input("输入用户ID或用户名: ").strip()
                self.ban_user(kw)
            elif choice == "5":
                kw = input("输入用户ID或用户名: ").strip()
                self.unban_user(kw)
            elif choice == "0":
                break
            else:
                print("[错误] 无效选择")