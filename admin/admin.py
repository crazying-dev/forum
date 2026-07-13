#!/usr/bin/env python3
"""
妖精论坛管理员内核

功能:
    1. 查看被举报的帖子列表
    2. 修改用户信息
    3. 删除帖子
    4. 删除评论
    5. 封禁/解封用户
    6. 查看所有用户
    7. 查看帖子详情

用法:
    # 交互模式（推荐）
    python admin/admin.py

    # 命令行模式
    python admin/admin.py reports
    python admin/admin.py users
    python admin/admin.py post <post_id>
    python admin/admin.py delete-post <post_id>
    python admin/admin.py delete-comment <comment_id>
    python admin/admin.py ban <user_id_or_name>
    python admin/admin.py unban <user_id_or_name>
    python admin/admin.py edit-user <查找键>=<查找值> <修改键>=<修改值>

嵌入使用:
    from admin.admin import AdminKernel
    kernel = AdminKernel()
    kernel.list_reports()
    kernel.delete_post("PS123456")
    kernel.ban_user("YJ123456")
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from api.database import execute_query, get_conn


class AdminKernel:
    """管理员内核（兼容旧接口，组合 UserKernel + PostKernel）。"""

    def __init__(self):
        self.user_kernel = UserKernel()
        self.post_kernel = PostKernel()

    def list_reports(self, status_filter=None):
        return self.post_kernel.list_reports(status_filter)

    def resolve_report(self, report_id):
        return self.post_kernel.resolve_report(report_id)

    def list_users(self):
        return self.user_kernel.list_users()

    def find_user(self, key, value):
        return self.user_kernel.find_user(key, value)

    def find_user_smart(self, identifier):
        return self.user_kernel.find_user_smart(identifier)

    def update_user(self, user_id, key, value):
        return self.user_kernel.update_user(user_id, key, value)

    def ban_user(self, user_id):
        return self.user_kernel.ban_user(user_id)

    def unban_user(self, user_id):
        return self.user_kernel.unban_user(user_id)

    def get_post_detail(self, post_id):
        return self.post_kernel.get_post_detail(post_id)

    def delete_post(self, post_id):
        return self.post_kernel.delete_post(post_id)

    def get_post_comments(self, post_id):
        return self.post_kernel.get_post_comments(post_id)

    def delete_comment(self, comment_id):
        return self.post_kernel.delete_comment(comment_id)

    def get_stats(self):
        return self.post_kernel.get_stats()


class UserKernel:
    """用户数据管理内核。"""

    @staticmethod
    def check():
        """检查内核是否可用。"""
        try:
            from api.database import execute_query
            execute_query("SELECT 1 FROM users LIMIT 1", fetch=True)
            return True
        except Exception:
            return False

    def list_users(self):
        """获取所有用户列表。"""
        results = execute_query(
            """SELECT id, name, avatar, email, gender, age, intro, vip, is_banned, created_at, last_login
               FROM users ORDER BY created_at DESC""",
            fetch_all=True
        ) or []
        users = []
        for r in results:
            users.append({
                "id": r[0], "name": r[1], "avatar": r[2], "email": r[3],
                "gender": r[4], "age": r[5], "intro": r[6], "vip": r[7],
                "is_banned": r[8],
                "created_at": str(r[9]) if r[9] else None,
                "last_login": str(r[10]) if r[10] else None,
            })
        return users

    def find_user(self, key, value):
        """查找用户。支持 id, name, email, avatar, gender, age, intro, vip 字段。"""
        allowed = ['id', 'name', 'email', 'avatar', 'gender', 'age', 'intro', 'vip']
        if key not in allowed:
            print(f"[错误] 不支持的查找字段: {key}，可用: {', '.join(allowed)}")
            return []
        results = execute_query(
            f"""SELECT id, name, avatar, email, gender, age, intro, vip, is_banned, created_at, last_login
                FROM users WHERE {key} = %s ORDER BY created_at DESC""",
            (value,), fetch_all=True
        ) or []
        users = []
        for r in results:
            users.append({
                "id": r[0], "name": r[1], "avatar": r[2], "email": r[3],
                "gender": r[4], "age": r[5], "intro": r[6], "vip": r[7],
                "is_banned": r[8],
                "created_at": str(r[9]) if r[9] else None,
                "last_login": str(r[10]) if r[10] else None,
            })
        return users

    def find_user_smart(self, identifier):
        """智能查找用户：先按ID查，查不到再按用户名查。"""
        user = self.find_user('id', identifier)
        if user:
            return user
        return self.find_user('name', identifier)

    def update_user(self, user_id, key, value):
        """修改用户信息。

        Args:
            user_id: 用户ID
            key: 字段名（name, avatar, email, gender, age, intro, vip, password, is_banned）
            value: 新值

        Returns:
            bool: 是否更新成功
        """
        allowed = ['name', 'avatar', 'email', 'gender', 'age', 'intro', 'vip', 'password', 'is_banned']
        if key not in allowed:
            print(f"[错误] 不支持的修改字段: {key}，可用: {', '.join(allowed)}")
            return False

        if key == 'password':
            from werkzeug.security import generate_password_hash
            value = generate_password_hash(value)

        affected = execute_query(
            f"UPDATE users SET {key} = %s WHERE id = %s",
            (value, user_id)
        )
        return affected > 0

    def ban_user(self, user_id):
        """封禁用户。"""
        return self.update_user(user_id, 'is_banned', 1)

    def unban_user(self, user_id):
        """解封用户。"""
        return self.update_user(user_id, 'is_banned', 0)


class PostKernel:
    """帖子管理与举报查看内核。"""

    @staticmethod
    def check():
        """检查内核是否可用。"""
        try:
            from api.database import execute_query
            execute_query("SELECT 1 FROM posts LIMIT 1", fetch=True)
            return True
        except Exception:
            return False

    # ========================
    # 举报管理
    # ========================

    def list_reports(self, status_filter=None):
        """查看被举报的帖子列表。"""
        sql = """
            SELECT r.id, r.post_id, r.reporter_id, r.reason, r.detail, r.status, r.created_at,
                   p.title, p.user_id, u.name AS author_name,
                   ru.name AS reporter_name
            FROM post_reports r
            LEFT JOIN posts p ON r.post_id = p.id
            LEFT JOIN users u ON p.user_id = u.id
            LEFT JOIN users ru ON r.reporter_id = ru.id
        """
        params = ()
        if status_filter is not None:
            sql += " WHERE r.status = %s"
            params = (status_filter,)
        sql += " ORDER BY r.created_at DESC"

        results = execute_query(sql, params, fetch_all=True) or []
        reports = []
        for r in results:
            reports.append({
                "id": r[0], "post_id": r[1], "reporter_id": r[2],
                "reason": r[3], "detail": r[4], "status": r[5],
                "created_at": str(r[6]) if r[6] else None,
                "post_title": r[7] or "[帖子已删除]",
                "post_author_id": r[8], "post_author": r[9] or "[未知]",
                "reporter_name": r[10] or "[未知]",
            })
        return reports

    def resolve_report(self, report_id):
        """将举报标记为已处理。"""
        affected = execute_query(
            "UPDATE post_reports SET status = 1 WHERE id = %s",
            (report_id,)
        )
        return affected > 0

    # ========================
    # 帖子管理
    # ========================

    def get_post_detail(self, post_id):
        """获取帖子详情（包含作者信息，不限制 status）。"""
        result = execute_query(
            """SELECT p.id, p.user_id, p.title, p.content, p.category, p.likes, p.views, p.status,
                      p.created_at, p.updated_at, u.name, u.avatar
               FROM posts p
               LEFT JOIN users u ON p.user_id = u.id
               WHERE p.id = %s""",
            (post_id,), fetch=True
        )
        if not result:
            return None
        return {
            "id": result[0], "user_id": result[1], "title": result[2],
            "content": result[3], "category": result[4], "likes": result[5],
            "views": result[6], "status": result[7],
            "created_at": str(result[8]) if result[8] else None,
            "updated_at": str(result[9]) if result[9] else None,
            "user_name": result[10] or "[未知]",
            "user_avatar": result[11],
        }

    def delete_post(self, post_id):
        """管理员删除帖子（绕过权限检查）。"""
        post = self.get_post_detail(post_id)
        if not post:
            return False, "帖子不存在"
        execute_query("DELETE FROM posts WHERE id = %s", (post_id,))
        return True, f"已删除帖子: {post['title']}"

    def get_post_comments(self, post_id):
        """获取帖子的所有评论（不限制 status）。"""
        results = execute_query(
            """SELECT c.id, c.post_id, c.user_id, c.content, c.parent_id, c.likes, c.status, c.created_at,
                      u.name, u.avatar
               FROM comments c
               LEFT JOIN users u ON c.user_id = u.id
               WHERE c.post_id = %s
               ORDER BY c.created_at DESC""",
            (post_id,), fetch_all=True
        ) or []
        comments = []
        for r in results:
            comments.append({
                "id": r[0], "post_id": r[1], "user_id": r[2],
                "content": r[3], "parent_id": r[4], "likes": r[5],
                "status": r[6],
                "created_at": str(r[7]) if r[7] else None,
                "user_name": r[8] or "[未知]",
                "user_avatar": r[9],
            })
        return comments

    def delete_comment(self, comment_id):
        """管理员删除评论（软删除，绕过权限检查）。"""
        row = execute_query(
            "SELECT id, post_id FROM comments WHERE id = %s",
            (comment_id,), fetch=True
        )
        if not row:
            return False, "评论不存在"
        execute_query("UPDATE comments SET status = 0 WHERE id = %s", (comment_id,))
        return True, f"已删除评论: {comment_id}"

    # ========================
    # 统计信息
    # ========================

    def get_stats(self):
        """获取论坛统计信息。"""
        user_count = execute_query("SELECT COUNT(*) FROM users", fetch=True)
        post_count = execute_query("SELECT COUNT(*) FROM posts WHERE status = 1", fetch=True)
        comment_count = execute_query("SELECT COUNT(*) FROM comments WHERE status = 1", fetch=True)
        report_pending = execute_query("SELECT COUNT(*) FROM post_reports WHERE status = 0", fetch=True)
        banned_count = execute_query("SELECT COUNT(*) FROM users WHERE is_banned = 1", fetch=True)
        return {
            "users": user_count[0] if user_count else 0,
            "posts": post_count[0] if post_count else 0,
            "comments": comment_count[0] if comment_count else 0,
            "pending_reports": report_pending[0] if report_pending else 0,
            "banned_users": banned_count[0] if banned_count else 0,
        }


# ========================
# CLI 交互层
# ========================

def _print_reports(reports):
    """打印举报列表。"""
    if not reports:
        print("[信息] 没有举报记录")
        return
    print(f"\n共 {len(reports)} 条举报记录")
    print("=" * 100)
    print(f"{'#':<5} {'举报ID':<8} {'帖子ID':<18} {'帖子标题':<20} {'举报人':<12} {'原因':<12} {'状态':<6} {'时间'}")
    print("-" * 100)
    for i, r in enumerate(reports, 1):
        status_str = "已处理" if r['status'] == 1 else "待处理"
        title = r['post_title'][:18] if r['post_title'] else "[已删除]"
        print(f"{i:<5} {r['id']:<8} {r['post_id']:<18} {title:<20} {r['reporter_name']:<12} {r['reason']:<12} {status_str:<6} {r['created_at']}")
    print("=" * 100)


def _print_users(users):
    """打印用户列表。"""
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


def _print_post_detail(post):
    """打印帖子详情。"""
    if not post:
        print("[信息] 帖子不存在")
        return
    status_str = "正常" if post['status'] == 1 else "已删除"
    print("\n" + "=" * 60)
    print(f"帖子ID:   {post['id']}")
    print(f"标题:     {post['title']}")
    print(f"作者:     {post['user_name']} ({post['user_id']})")
    print(f"分类:     {post['category']}")
    print(f"状态:     {status_str}")
    print(f"点赞:     {post['likes']}  浏览: {post['views']}")
    print(f"创建时间: {post['created_at']}")
    print(f"更新时间: {post['updated_at']}")
    print("-" * 60)
    print(f"内容:\n{post['content']}")
    print("=" * 60)


def _print_comments(comments):
    """打印评论列表。"""
    if not comments:
        print("[信息] 没有评论")
        return
    print(f"\n共 {len(comments)} 条评论")
    print("=" * 90)
    print(f"{'#':<5} {'评论ID':<18} {'用户名':<12} {'状态':<6} {'内容':<30} {'时间'}")
    print("-" * 90)
    for i, c in enumerate(comments, 1):
        status_str = "正常" if c['status'] == 1 else "已删除"
        content = c['content'][:28] if c['content'] else ""
        print(f"{i:<5} {c['id']:<18} {c['user_name']:<12} {status_str:<6} {content:<30} {c['created_at']}")
    print("=" * 90)


def _confirm(prompt):
    """确认对话框。"""
    return input(f"{prompt} [y/N]: ").strip().lower() == 'y'


def _select_from_list(items, label="临时ID"):
    """从列表中选择一项，返回索引。"""
    if not items:
        return -1
    if len(items) == 1:
        return 0
    while True:
        choice = input(f"请输入{label} (1-{len(items)}) 或 q 退出: ").strip()
        if choice.lower() == 'q':
            return -1
        try:
            idx = int(choice)
            if 1 <= idx <= len(items):
                return idx - 1
            print(f"[错误] 请输入 1-{len(items)} 之间的数字")
        except ValueError:
            print("[错误] 请输入有效的数字")


def cli_reports(kernel):
    """举报列表交互。"""
    print("\n--- 举报列表 ---")
    print("  1. 查看全部举报")
    print("  2. 查看待处理举报")
    print("  3. 查看已处理举报")
    sub = input("选择 (默认1): ").strip() or "1"

    status = None
    if sub == "2":
        status = 0
    elif sub == "3":
        status = 1

    reports = kernel.list_reports(status)
    _print_reports(reports)

    if not reports:
        return

    # 提供进一步操作
    print("\n可执行操作:")
    print("  1. 查看帖子详情")
    print("  2. 删除被举报的帖子")
    print("  3. 标记举报为已处理")
    print("  0. 返回")
    action = input("选择: ").strip()

    if action == "1":
        idx = _select_from_list(reports)
        if idx >= 0:
            post = kernel.get_post_detail(reports[idx]['post_id'])
            _print_post_detail(post)
    elif action == "2":
        idx = _select_from_list(reports)
        if idx >= 0:
            r = reports[idx]
            if _confirm(f"确认删除帖子 '{r['post_title']}'?"):
                ok, msg = kernel.delete_post(r['post_id'])
                print(f"[{'成功' if ok else '失败'}] {msg}")
                if ok and r['status'] == 0:
                    kernel.resolve_report(r['id'])
                    print("[信息] 举报已标记为已处理")
    elif action == "3":
        idx = _select_from_list(reports)
        if idx >= 0:
            r = reports[idx]
            if kernel.resolve_report(r['id']):
                print("[成功] 举报已标记为已处理")
            else:
                print("[失败] 操作失败")


def cli_users(kernel):
    """用户列表交互。"""
    print("\n--- 用户管理 ---")
    print("  1. 查看所有用户")
    print("  2. 查找用户")
    print("  3. 修改用户信息")
    print("  4. 封禁用户")
    print("  5. 解封用户")
    print("  0. 返回")
    action = input("选择: ").strip()

    if action == "1":
        users = kernel.list_users()
        _print_users(users)

    elif action == "2":
        print("可用字段: id, name, email, avatar, gender, age, intro, vip")
        key = input("查找字段: ").strip()
        value = input("查找值: ")
        users = kernel.find_user(key, value)
        _print_users(users)

    elif action == "3":
        identifier = input("输入用户ID或用户名: ").strip()
        users = kernel.find_user_smart(identifier)
        if not users:
            print("[信息] 未找到用户")
            return
        _print_users(users)
        idx = _select_from_list(users)
        if idx < 0:
            return
        user = users[idx]
        print(f"\n已选择: {user['name']} ({user['id']})")
        print("可修改字段: name, avatar, email, gender, age, intro, vip, password, is_banned")
        key = input("修改字段: ").strip()
        value = input("修改值: ")
        if _confirm(f"确认将 {user['name']} 的 {key} 修改为: {value}?"):
            if kernel.update_user(user['id'], key, value):
                print("[成功] 用户数据已更新")
            else:
                print("[失败] 更新未生效")

    elif action == "4":
        identifier = input("输入用户ID或用户名: ").strip()
        users = kernel.find_user_smart(identifier)
        if not users:
            print("[信息] 未找到用户")
            return
        _print_users(users)
        idx = _select_from_list(users)
        if idx >= 0:
            user = users[idx]
            if _confirm(f"确认封禁用户 {user['name']} ({user['id']})?"):
                if kernel.ban_user(user['id']):
                    print("[成功] 用户已被封禁")
                else:
                    print("[失败] 操作失败")

    elif action == "5":
        identifier = input("输入用户ID或用户名: ").strip()
        users = kernel.find_user_smart(identifier)
        if not users:
            print("[信息] 未找到用户")
            return
        _print_users(users)
        idx = _select_from_list(users)
        if idx >= 0:
            user = users[idx]
            if _confirm(f"确认解封用户 {user['name']} ({user['id']})?"):
                if kernel.unban_user(user['id']):
                    print("[成功] 用户已被解封")
                else:
                    print("[失败] 操作失败")


def cli_posts(kernel):
    """帖子管理交互。"""
    print("\n--- 帖子管理 ---")
    print("  1. 查看帖子详情")
    print("  2. 删除帖子")
    print("  3. 查看帖子评论")
    print("  4. 删除评论")
    print("  0. 返回")
    action = input("选择: ").strip()

    if action == "1":
        post_id = input("输入帖子ID: ").strip()
        post = kernel.get_post_detail(post_id)
        _print_post_detail(post)

    elif action == "2":
        post_id = input("输入帖子ID: ").strip()
        post = kernel.get_post_detail(post_id)
        if not post:
            print("[信息] 帖子不存在")
            return
        _print_post_detail(post)
        if _confirm(f"确认删除帖子 '{post['title']}'?"):
            ok, msg = kernel.delete_post(post_id)
            print(f"[{'成功' if ok else '失败'}] {msg}")

    elif action == "3":
        post_id = input("输入帖子ID: ").strip()
        comments = kernel.get_post_comments(post_id)
        _print_comments(comments)

    elif action == "4":
        comment_id = input("输入评论ID: ").strip()
        if _confirm(f"确认删除评论 {comment_id}?"):
            ok, msg = kernel.delete_comment(comment_id)
            print(f"[{'成功' if ok else '失败'}] {msg}")


def cli_stats(kernel):
    """显示统计信息。"""
    stats = kernel.get_stats()
    print("\n" + "=" * 40)
    print("  论坛统计信息")
    print("=" * 40)
    print(f"  总用户数:     {stats['users']}")
    print(f"  帖子总数:     {stats['posts']}")
    print(f"  评论总数:     {stats['comments']}")
    print(f"  待处理举报:   {stats['pending_reports']}")
    print(f"  已封禁用户:   {stats['banned_users']}")
    print("=" * 40)


def main():
    """CLI 主入口。"""
    kernel = AdminKernel()

    # 命令行直接执行模式
    if len(sys.argv) >= 2:
        cmd = sys.argv[1]

        if cmd == "reports":
            reports = kernel.list_reports()
            _print_reports(reports)
            return

        if cmd == "users":
            users = kernel.list_users()
            _print_users(users)
            return

        if cmd == "stats":
            cli_stats(kernel)
            return

        if cmd == "post" and len(sys.argv) >= 3:
            post = kernel.get_post_detail(sys.argv[2])
            _print_post_detail(post)
            return

        if cmd == "delete-post" and len(sys.argv) >= 3:
            ok, msg = kernel.delete_post(sys.argv[2])
            print(f"[{'成功' if ok else '失败'}] {msg}")
            return

        if cmd == "delete-comment" and len(sys.argv) >= 3:
            ok, msg = kernel.delete_comment(sys.argv[2])
            print(f"[{'成功' if ok else '失败'}] {msg}")
            return

        if cmd == "ban" and len(sys.argv) >= 3:
            users = kernel.find_user_smart(sys.argv[2])
            if not users:
                print("[信息] 未找到用户")
                return
            for u in users:
                if kernel.ban_user(u['id']):
                    print(f"[成功] 已封禁: {u['name']} ({u['id']})")
            return

        if cmd == "unban" and len(sys.argv) >= 3:
            users = kernel.find_user_smart(sys.argv[2])
            if not users:
                print("[信息] 未找到用户")
                return
            for u in users:
                if kernel.unban_user(u['id']):
                    print(f"[成功] 已解封: {u['name']} ({u['id']})")
            return

        if cmd == "edit-user" and len(sys.argv) >= 4:
            # python admin.py edit-user "name=张三" "vip=1"
            def parse(arg):
                if '=' not in arg:
                    return None, None
                k, v = arg.split('=', 1)
                return k.strip(), v
            skey, sval = parse(sys.argv[2])
            ukey, uval = parse(sys.argv[3])
            if not skey or not ukey:
                print("[错误] 参数格式错误，必须使用 key=value")
                return
            users = kernel.find_user(skey, sval)
            if not users:
                print("[信息] 未找到用户")
                return
            _print_users(users)
            idx = _select_from_list(users)
            if idx >= 0:
                user = users[idx]
                if _confirm(f"确认将 {user['name']} 的 {ukey} 修改为: {uval}?"):
                    if kernel.update_user(user['id'], ukey, uval):
                        print("[成功] 用户数据已更新")
                    else:
                        print("[失败] 更新未生效")
            return

        print(__doc__)
        return

    # 交互模式
    print("=" * 50)
    print("  妖精论坛管理员内核")
    print("=" * 50)

    while True:
        print("\n主菜单:")
        print("  1. 举报管理")
        print("  2. 用户管理")
        print("  3. 帖子管理")
        print("  4. 统计信息")
        print("  0. 退出")
        choice = input("选择: ").strip()

        if choice == "1":
            cli_reports(kernel)
        elif choice == "2":
            cli_users(kernel)
        elif choice == "3":
            cli_posts(kernel)
        elif choice == "4":
            cli_stats(kernel)
        elif choice == "0":
            print("[退出] 再见")
            break
        else:
            print("[错误] 无效选择")


if __name__ == '__main__':
    main()
