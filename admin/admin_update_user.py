#!/usr/bin/env python3
"""
管理员用户修改工具

用法:
    # 命令行模式
    python admin_update_user.py "<查找键>=<查找值>" "<修改键>=<修改值>"

    # 交互模式（支持所有特殊字符，推荐）
    python admin_update_user.py -i

示例:
    python admin_update_user.py "name=张三" "vip=1"
    python admin_update_user.py "email=zhangsan@example.com" "intro=新简介"
    python admin_update_user.py "id=YJ123456" "age=25"

    PowerShell 中含特殊字符时可使用单引号:
        python admin_update_user.py "name=卡里" 'name=卡里|<p class="TimeWithUserNameAPI"></p>'

    若 Shell 转义仍有问题，请使用交互模式:
        python admin_update_user.py -i
"""

import sys
sys.path.insert(0, '.')

from api.database import execute_query, get_conn


def parse_arg(arg):
    """解析 key=value 格式的参数，支持值中包含 = 和特殊字符"""
    if '=' not in arg:
        return None, None
    key, value = arg.split('=', 1)
    return key.strip(), value  # 不 strip value，保留原始内容（含特殊字符）


def find_users(search_key, search_value):
    """根据条件查找用户。"""
    allowed_search_keys = ['id', 'name', 'avatar', 'email', 'gender', 'age', 'intro', 'vip']
    if search_key not in allowed_search_keys:
        print(f"[错误] 不支持的查找字段: {search_key}")
        print(f"支持的字段: {', '.join(allowed_search_keys)}")
        return []

    try:
        results = execute_query(
            """
            SELECT id, name, avatar, email, gender, age, intro, vip, created_at, last_login
            FROM users
            WHERE {} = %s
            ORDER BY created_at DESC
            """.format(search_key),
            (search_value,),
            fetch_all=True
        )
    except Exception as e:
        print(f"[错误] 查询失败: {e}")
        return []

    users = []
    for r in results:
        users.append({
            "id": r[0],
            "name": r[1],
            "avatar": r[2],
            "email": r[3],
            "gender": r[4],
            "age": r[5],
            "intro": r[6],
            "vip": r[7],
            "created_at": str(r[8]) if r[8] else None,
            "last_login": str(r[9]) if r[9] else None,
        })
    return users


def print_user_list(users):
    """打印用户列表，带临时自增ID。"""
    print("\n" + "=" * 90)
    print(f"{'临时ID':<8} {'用户ID':<22} {'用户名':<14} {'邮箱':<26} {'VIP':<5} {'年龄':<6}")
    print("-" * 90)
    for i, user in enumerate(users, 1):
        print(f"{i:<8} {user['id']:<22} {user['name']:<14} {user['email']:<26} {str(user['vip']):<5} {str(user['age']):<6}")
    print("=" * 90)


def update_user(user_id, update_key, update_value):
    """更新指定用户的数据。"""
    allowed_update_keys = ['id', 'name', 'avatar', 'email', 'gender', 'age', 'intro', 'vip', 'password']
    if update_key not in allowed_update_keys:
        print(f"[错误] 不支持的修改字段: {update_key}")
        print(f"支持的字段: {', '.join(allowed_update_keys)}")
        return False

    try:
        if update_key == 'password':
            from werkzeug.security import generate_password_hash
            update_value = generate_password_hash(update_value)

        affected = execute_query(
            f"UPDATE users SET {update_key} = %s WHERE id = %s",
            (update_value, user_id)
        )
        return affected > 0
    except Exception as e:
        print(f"[错误] 更新失败: {e}")
        return False


def interactive_mode():
    """交互模式，逐项输入，完全避免 Shell 转义问题。"""
    print("=" * 50)
    print("  管理员用户修改工具 - 交互模式")
    print("=" * 50)

    allowed_search_keys = ['id', 'name', 'avatar', 'email', 'gender', 'age', 'intro', 'vip']
    allowed_update_keys = ['id', 'name', 'avatar', 'email', 'gender', 'age', 'intro', 'vip', 'password']

    # 输入查找条件
    print(f"\n可用查找字段: {', '.join(allowed_search_keys)}")
    search_key = input("查找字段: ").strip()
    if search_key not in allowed_search_keys:
        print(f"[错误] 不支持的查找字段: {search_key}")
        sys.exit(1)

    search_value = input("查找值: ")  # 不 strip，保留原始内容

    # 查找用户
    print(f"\n[查找条件] {search_key} = {search_value}")
    print("-" * 40)
    users = find_users(search_key, search_value)

    if not users:
        print("[结果] 未找到匹配用户")
        sys.exit(0)

    # 选择用户
    if len(users) == 1:
        user = users[0]
        print(f"\n找到 1 个用户: {user['name']} ({user['id']})")
    else:
        print(f"\n找到 {len(users)} 个匹配用户，请选择:")
        print_user_list(users)
        while True:
            choice = input(f"请输入临时ID (1-{len(users)}) 或 q 退出: ").strip()
            if choice.lower() == 'q':
                print("[取消] 操作已取消")
                sys.exit(0)
            try:
                idx = int(choice)
                if 1 <= idx <= len(users):
                    user = users[idx - 1]
                    print(f"\n[已选择] #{idx}: {user['name']} ({user['id']})")
                    break
                else:
                    print(f"[错误] 临时ID 必须在 1-{len(users)} 之间")
            except ValueError:
                print("[错误] 请输入有效的数字")

    # 输入修改内容
    print(f"\n可用修改字段: {', '.join(allowed_update_keys)}")
    update_key = input("修改字段: ").strip()
    if update_key not in allowed_update_keys:
        print(f"[错误] 不支持的修改字段: {update_key}")
        sys.exit(1)

    update_value = input("修改值: ")  # 不 strip，保留原始内容

    # 确认修改
    print(f"\n[确认] 将用户 {user['name']} ({user['id']}) 的 {update_key} 修改为: {update_value}")
    confirm = input("确认修改? [y/N]: ").strip().lower()
    if confirm == 'y':
        success = update_user(user['id'], update_key, update_value)
        if success:
            print("[成功] 用户数据已更新")
        else:
            print("[失败] 更新未生效")
    else:
        print("[取消] 操作已取消")


def main():
    # 交互模式
    if len(sys.argv) >= 2 and sys.argv[1] in ('-i', '--interactive'):
        interactive_mode()
        return

    if len(sys.argv) < 3:
        print(__doc__)
        print("\n[错误] 参数不足，需要两个参数：查找条件和修改内容")
        print("[提示] 使用 -i 或 --interactive 进入交互模式（支持所有特殊字符）")
        sys.exit(1)

    search_key, search_value = parse_arg(sys.argv[1])
    update_key, update_value = parse_arg(sys.argv[2])

    if not search_key or not update_key:
        print("[错误] 参数格式错误，必须使用 key=value 格式")
        sys.exit(1)

    print(f"[查找条件] {search_key} = {search_value}")
    print(f"[修改内容] {update_key} = {update_value}")
    print("-" * 40)

    users = find_users(search_key, search_value)

    if not users:
        print("[结果] 未找到匹配用户")
        sys.exit(0)

    if len(users) == 1:
        user = users[0]
        print(f"\n找到 1 个用户: {user['name']} ({user['id']})")
        confirm = input("确认修改? [y/N]: ").strip().lower()
        if confirm == 'y':
            success = update_user(user['id'], update_key, update_value)
            if success:
                print("[成功] 用户数据已更新")
            else:
                print("[失败] 更新未生效")
        else:
            print("[取消] 操作已取消")
    else:
        print(f"\n找到 {len(users)} 个匹配用户，请选择要修改的用户:")
        print_user_list(users)

        while True:
            choice = input(f"请输入临时ID (1-{len(users)}) 或 q 退出: ").strip()
            if choice.lower() == 'q':
                print("[取消] 操作已取消")
                sys.exit(0)
            try:
                idx = int(choice)
                if 1 <= idx <= len(users):
                    selected = users[idx - 1]
                    print(f"\n[已选择] #{idx}: {selected['name']} ({selected['id']})")
                    confirm = input("确认修改? [y/N]: ").strip().lower()
                    if confirm == 'y':
                        success = update_user(selected['id'], update_key, update_value)
                        if success:
                            print("[成功] 用户数据已更新")
                        else:
                            print("[失败] 更新未生效")
                    else:
                        print("[取消] 操作已取消")
                    break
                else:
                    print(f"[错误] 临时ID 必须在 1-{len(users)} 之间")
            except ValueError:
                print("[错误] 请输入有效的数字")


if __name__ == '__main__':
    main()
