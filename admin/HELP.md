# 妖精论坛管理员内核 - 使用文档

## 目录

- [快速开始](#快速开始)
- [交互模式](#交互模式)
- [命令行模式](#命令行模式)
- [嵌入使用](#嵌入使用)
- [功能详解](#功能详解)
  - [举报管理](#举报管理)
  - [用户管理](#用户管理)
  - [帖子管理](#帖子管理)
  - [统计信息](#统计信息)
- [常见问题](#常见问题)

---

## 快速开始

### 环境要求

- Python 3.11+
- PostgreSQL 数据库（Neon 或兼容）
- 依赖：`psycopg2-binary`、`python-dotenv`、`Werkzeug`（密码哈希用）

### 配置

在 `forum-app` 目录下创建 `.env` 文件，添加数据库连接：

```env
DATABASE_URL=postgresql://user:password@host/dbname?sslmode=require
```

### 启动

```bash
cd forum-app

# 交互模式（推荐新手）
python admin/admin.py

# 查看帮助
python admin/admin.py -h
```

---

## 交互模式

直接运行 `python admin/admin.py` 进入菜单式交互界面，全程按提示操作即可。

### 主菜单

```
  1. 举报管理
  2. 用户管理
  3. 帖子管理
  4. 统计信息
  0. 退出
```

输入对应数字进入子菜单，输入 `0` 返回上一级或退出。

### 通用操作

- **选择条目**：输入临时 ID（数字）后回车
- **取消操作**：输入 `q` 后回车
- **确认操作**：输入 `y` 后回车
- **默认选项**：直接回车使用括号中的默认值

---

## 命令行模式

适合脚本自动化或快速操作。

### 举报管理

```bash
# 查看所有举报
python admin/admin.py reports

# 查看待处理举报（交互模式中筛选）
```

### 用户管理

```bash
# 查看所有用户
python admin/admin.py users

# 封禁用户（支持ID或用户名）
python admin/admin.py ban YJ1234567890
python admin/admin.py ban "用户名"

# 解封用户
python admin/admin.py unban YJ1234567890
python admin/admin.py unban "用户名"

# 修改用户信息
python admin/admin.py edit-user "name=张三" "vip=1"
python admin/admin.py edit-user "id=YJ123" "is_banned=1"
python admin/admin.py edit-user "email=a@b.com" "intro=新简介"
```

### 帖子管理

```bash
# 查看帖子详情
python admin/admin.py post PS1234567890

# 删除帖子
python admin/admin.py delete-post PS1234567890

# 删除评论
python admin/admin.py delete-comment CM1234567890
```

### 统计信息

```bash
# 查看论坛概况
python admin/admin.py stats
```

---

## 嵌入使用

`AdminKernel` 类可直接导入到其他 Python 脚本中使用。

### 基本用法

```python
import sys
sys.path.insert(0, 'forum-app')  # 或你的项目路径

from admin.admin import AdminKernel

kernel = AdminKernel()

# 查看举报
reports = kernel.list_reports()
for r in reports:
    print(r['post_title'], r['reason'])

# 封禁用户
kernel.ban_user("YJ1234567890")

# 删除帖子
ok, msg = kernel.delete_post("PS1234567890")
```

### 全部 API

#### 举报管理

| 方法 | 参数 | 返回值 | 说明 |
|------|------|--------|------|
| `list_reports(status_filter=None)` | status_filter: None/0/1 | list | 举报列表 |
| `resolve_report(report_id)` | report_id: int | bool | 标记为已处理 |

#### 用户管理

| 方法 | 参数 | 返回值 | 说明 |
|------|------|--------|------|
| `list_users()` | - | list | 所有用户 |
| `find_user(key, value)` | key: 字段名, value: 值 | list | 按字段查找 |
| `find_user_smart(identifier)` | identifier: ID或用户名 | list | 智能查找 |
| `update_user(user_id, key, value)` | user_id, key, value | bool | 修改用户信息 |
| `ban_user(user_id)` | user_id | bool | 封禁 |
| `unban_user(user_id)` | user_id | bool | 解封 |

**`find_user` 支持的字段**：`id`、`name`、`email`、`avatar`、`gender`、`age`、`intro`、`vip`

**`update_user` 支持的字段**：`name`、`avatar`、`email`、`gender`、`age`、`intro`、`vip`、`password`、`is_banned`

#### 帖子管理

| 方法 | 参数 | 返回值 | 说明 |
|------|------|--------|------|
| `get_post_detail(post_id)` | post_id | dict/None | 帖子详情 |
| `delete_post(post_id)` | post_id | (bool, str) | 删除帖子 |
| `get_post_comments(post_id)` | post_id | list | 帖子评论列表 |
| `delete_comment(comment_id)` | comment_id | (bool, str) | 删除评论 |

#### 统计信息

| 方法 | 参数 | 返回值 | 说明 |
|------|------|--------|------|
| `get_stats()` | - | dict | 论坛统计数据 |

---

## 功能详解

### 举报管理

举报分为两种状态：
- **待处理**（status=0）：新提交的举报
- **已处理**（status=1）：管理员已查看并处理

**处理流程**：
1. 进入举报管理 → 查看待处理举报
2. 查看帖子详情确认是否违规
3. 选择删除帖子（自动标记举报为已处理）
4. 或手动标记举报为已处理

### 用户管理

#### 用户状态字段

| 字段 | 类型 | 说明 |
|------|------|------|
| `is_banned` | INTEGER | 0=正常, 1=封禁 |
| `vip` | VARCHAR | '0'=普通, '1'=VIP |
| `gender` | INTEGER | 0=保密, 1=男, 2=女 |
| `age` | VARCHAR | yyyymmdd 格式的出生日期 |

#### 封禁效果

- 被封禁用户无法登录（登录时返回"该账号已被封禁"）
- 已登录的封禁用户刷新页面后会被踢出
- 用户的帖子和评论不受影响（可单独删除）

### 帖子管理

#### 删除策略

- **帖子删除**：物理删除（`DELETE FROM posts`），级联删除关联的点赞、收藏、评论、举报
- **评论删除**：软删除（`status = 0`），数据保留但不再显示

---

## 常见问题

### Q: 运行时报错 `ModuleNotFoundError: No module named 'api'`

A: 确保从 `forum-app` 目录运行脚本，或手动添加路径：
```bash
cd forum-app
python admin/admin.py
```

### Q: 运行时报错 `DATABASE_URL 环境变量未设置`

A: 在 `forum-app` 目录下创建 `.env` 文件，添加数据库连接字符串。

### Q: 封禁用户后，用户还能访问吗？

A: 已登录的用户在 token/session 过期前仍可访问，但刷新或重新登录会被拒绝。

### Q: 删除的帖子能恢复吗？

A: 不能。帖子是物理删除，删除前请确认。评论是软删除（status=0），可通过数据库手动恢复。

### Q: 如何批量操作？

A: 编写 Python 脚本导入 `AdminKernel` 类，循环调用对应方法即可。

```python
from admin.admin import AdminKernel

kernel = AdminKernel()
user_ids = ["YJ123", "YJ456", "YJ789"]
for uid in user_ids:
    kernel.ban_user(uid)
    print(f"已封禁: {uid}")
```

### Q: 密码修改后用户怎么登录？

A: 直接使用新密码登录即可。密码会自动使用 Werkzeug 的哈希算法存储。
