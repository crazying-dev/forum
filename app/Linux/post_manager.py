#!/usr/bin/env python3
import sys
import os

APP_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, APP_DIR)


def print_reports(reports):
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


def print_post_detail(post):
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


def print_comments(comments):
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


def confirm(prompt):
    return input(f"{prompt} [y/N]: ").strip().lower() == 'y'


class PostManager:

    def __init__(self, api_client):
        self.api = api_client

    def list_reports(self):
        reports = self.api.list_reports()
        print_reports(reports)
        return reports

    def resolve_report(self, report_id):
        return self.api.resolve_report(report_id)

    def show_post(self, post_id):
        post = self.api.get_post_detail(post_id)
        print_post_detail(post)

    def delete_post(self, post_id):
        result = self.api.delete_post(post_id)
        if result:
            if isinstance(result, tuple):
                ok, msg = result
                print(f"[{'成功' if ok else '失败'}] {msg}")
            else:
                print("[成功] 帖子已删除")
        else:
            print("[失败] 删除失败")

    def show_comments(self, post_id):
        comments = self.api.get_post_comments(post_id)
        print_comments(comments)

    def delete_comment(self, comment_id):
        result = self.api.delete_comment(comment_id)
        if result:
            if isinstance(result, tuple):
                ok, msg = result
                print(f"[{'成功' if ok else '失败'}] {msg}")
            else:
                print("[成功] 评论已删除")
        else:
            print("[失败] 删除失败")

    def get_stats(self):
        return self.api.get_stats()

    def run(self):
        while True:
            print("\n" + "=" * 50)
            print("  帖子管理")
            print("=" * 50)
            print("\n菜单:")
            print("  1. 查看举报列表")
            print("  2. 查看帖子详情")
            print("  3. 删除帖子")
            print("  4. 查看帖子评论")
            print("  5. 删除评论")
            print("  0. 返回")
            choice = input("\n选择: ").strip()

            if choice == "1":
                reports = self.list_reports()
                if reports:
                    print("\n操作:")
                    print("  1. 标记举报已处理")
                    print("  2. 删除被举报帖子")
                    sub = input("选择: ").strip()
                    if sub == "1":
                        try:
                            idx = int(input("输入序号: ")) - 1
                            if 0 <= idx < len(reports):
                                if self.resolve_report(reports[idx]['id']):
                                    print("[成功] 举报已标记为已处理")
                        except ValueError:
                            print("[错误] 输入无效")
                    elif sub == "2":
                        try:
                            idx = int(input("输入序号: ")) - 1
                            if 0 <= idx < len(reports):
                                r = reports[idx]
                                self.delete_post(r['post_id'])
                                if r['status'] == 0:
                                    self.resolve_report(r['id'])
                                    print("[信息] 举报已标记为已处理")
                        except ValueError:
                            print("[错误] 输入无效")
            elif choice == "2":
                post_id = input("输入帖子ID: ").strip()
                self.show_post(post_id)
            elif choice == "3":
                post_id = input("输入帖子ID: ").strip()
                self.delete_post(post_id)
            elif choice == "4":
                post_id = input("输入帖子ID: ").strip()
                self.show_comments(post_id)
            elif choice == "5":
                comment_id = input("输入评论ID: ").strip()
                self.delete_comment(comment_id)
            elif choice == "0":
                break
            else:
                print("[错误] 无效选择")