# Plan: 妖精论坛代码重构

- **日期**: 2026-07-29
- **状态**: Approved
- **相关**: 无

## 背景

当前项目两个核心文件 `main/main.py`（1413行）和 `api/database.py`（1661行）过于庞大，所有路由、中间件、业务逻辑、数据访问全部混杂在一起，严重降低了代码的可读性和可维护性。

- `main/main.py`：同时包含 Flask 初始化、中间件（CSRF/限流/gzip）、用户包装类、30+ 路由（分散在页面、认证、用户、帖子、评论、世界频道、搜索等功能域）
- `api/database.py`：所有数据库操作（用户、帖子、评论、关注、收藏、世界频道、验证码、搜索）全在一个文件中
- `Email.py`：游离在根目录，应纳入项目包

## 目标

1. 按功能域拆分路由 → Flask Blueprint
2. 按领域拆分数据库操作 → 独立模块
3. 抽取公共基础设施（中间件、工具函数）→ 独立模块
4. 全中文注释和文档字符串
5. 保持对 `index.py`（Vercel 入口）的兼容

## 非目标（不在此计划内）

- 不改变路由 URL 路径（向前兼容）
- 不改动模板文件（`main/templates/`）
- 不改动 Vercel 部署配置
- 不添加新功能

## 需求摘要

- 路由按 Blueprint 拆分：页面 / 认证 / 用户 / 帖子 / 评论 / 世界频道 / 搜索
- 数据库按领域拆分：用户 / 帖子 / 评论 / 关注收藏 / 世界频道 / 验证 / 搜索
- 中间件独立：CSRF 保护、速率限制、gzip 压缩、安全响应头
- 工具函数独立：缓存、辅助函数
- 代码使用英文标识符，注释和文档使用中文

## 实施步骤

### 第一步：建立新项目结构

创建 `app/` 包目录树：

```
app/
├── __init__.py          # 应用工厂
├── 配置.py              # 配置常量（从 api/config.py 迁移）
├── 扩展.py              # CORS、Flask-Login 等扩展初始化
├── 中间件.py            # CSRF 保护、速率限制、gzip、安全头
├── 路由/
│   ├── __init__.py      # 注册所有蓝图
│   ├── 页面.py          # 页面路由
│   ├── 认证.py          # 认证 API
│   ├── 用户.py          # 用户 API
│   ├── 帖子.py          # 帖子 API
│   ├── 评论.py          # 评论 API
│   ├── 世界.py          # 世界频道 API
│   └── 搜索.py          # 搜索 API
├── 数据/
│   ├── __init__.py      # 连接管理 + 统一导出
│   ├── 用户.py          # 用户 CRUD
│   ├── 帖子.py          # 帖子 CRUD
│   ├── 评论.py          # 评论 CRUD
│   ├── 世界.py          # 世界频道
│   ├── 关注.py          # 关注/收藏
│   └── 验证.py          # 验证码/Token
└── 工具/
    ├── __init__.py
    ├── 缓存.py          # 缓存实现
    └── 辅助.py          # 辅助函数
```

### 第二步：迁移数据库层

1. 创建 `app/数据/__init__.py` — 从 `api/config.py` 移入配置、从 `api/database.py` 移入连接管理（`get_conn`、`execute_query`、`init_pool` 等）
2. 按领域拆分 `api/database.py` 中的函数到对应模块
3. 保留 `api/database.py` 作为兼容桥接层（`from app.数据 import *`），确保现有引用不中断

### 第三步：迁移基础设施

1. 创建 `app/配置.py` — 从 `api/config.py` 移入配置常量
2. 创建 `app/扩展.py` — Flask 扩展初始化（CORS、LoginManager、ProxyFix）
3. 创建 `app/中间件.py` — CSRF 保护、速率限制、gzip 压缩、安全响应头
4. 创建 `app/工具/缓存.py` — 从 `api/cache.py` 移入
5. 创建 `app/工具/辅助.py` — 工具函数（`safe_html`、`strip_easter_egg`、邮件发送等）

### 第四步：迁移路由层

1. 创建 `app/路由/__init__.py` — 注册所有蓝图，统一路由配置
2. 将 `main/main.py` 中的路由按功能域拆分到各蓝图文件
3. `main/main.py` 改为导入并注册蓝图，保留 `app` 实例供 Vercel 使用

### 第五步：清理与验证

1. 确认 `index.py` 的 `from main.main import app` 仍然可用
2. 确认 `api/database.py` 兼容桥接正常工作
3. 验证所有路由 URL 路径不变

## 需要修改的文件

### 新文件（创建）

- `app/__init__.py` — 应用工厂
- `app/配置.py` — 配置
- `app/扩展.py` — 扩展注册
- `app/中间件.py` — 中间件
- `app/路由/__init__.py`
- `app/路由/页面.py`
- `app/路由/认证.py`
- `app/路由/用户.py`
- `app/路由/帖子.py`
- `app/路由/评论.py`
- `app/路由/世界.py`
- `app/路由/搜索.py`
- `app/数据/__init__.py`
- `app/数据/用户.py`
- `app/数据/帖子.py`
- `app/数据/评论.py`
- `app/数据/世界.py`
- `app/数据/关注.py`
- `app/数据/验证.py`
- `app/工具/__init__.py`
- `app/工具/缓存.py`
- `app/工具/辅助.py`

### 现有文件（修改）

- `main/main.py` — 精简为 app 初始化 + 蓝图注册
- `api/database.py` — 改为从 `app.数据` 导入的桥接层（或保留为新架构的服务）
- `api/config.py` — 改为从 `app.配置` 导入的桥接层
- `api/cache.py` — 改为从 `app.工具.缓存` 导入的桥接层

## 风险与注意事项

| 风险 | 缓解措施 |
|------|----------|
| 跨模块引用断裂 | 保留旧模块作为桥接层，逐步迁移 |
| Blueprint 注册顺序影响中间件 | 明确中间件注册在蓝图之前 |
| `current_user` 上下文丢失 | Blueprint 中正确初始化 LoginManager |
| 模板路径 `PATH/base.html` 不变 | 确保 `template_folder` 配置正确 |
| Vercel 部署中断 | `index.py` 入口不变 |

## 开放问题

- [ ] 是否保留 `api/database.py` 作为桥接层，还是直接迁移完后删除？
- [ ] 邮件发送 (`Email.py`) 是否需要移入 `app/工具/辅助.py`？
- [ ] 是否为安全性验证（密码哈希、盐值）单独创建模块？