from dotenv import load_dotenv
import os

load_dotenv(verbose=True)
database_url = os.getenv("DATABASE_URL")

CREATE_USER_TABLE_SQL =   """
CREATE TABLE IF NOT EXISTS users (
    id VARCHAR(64) PRIMARY KEY,
    name VARCHAR(64) UNIQUE NOT NULL,
    avatar TEXT NOT NULL,
    email VARCHAR(255) UNIQUE NOT NULL,
    password VARCHAR(255) NOT NULL,
    gender INTEGER DEFAULT 0,
    age VARCHAR(32) DEFAULT '',
    intro TEXT DEFAULT '',
    vip VARCHAR(32) NOT NULL DEFAULT '0',
    prefix VARCHAR(32) DEFAULT '',
    is_banned INTEGER NOT NULL DEFAULT 0,
    email_verified INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_login TIMESTAMP
);
"""

CREATE_POST_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS posts (
    id VARCHAR(64) PRIMARY KEY,
    user_id VARCHAR(64) NOT NULL,
    title VARCHAR(255) NOT NULL,
    content TEXT NOT NULL,
    category VARCHAR(64) DEFAULT 'general',
    likes INTEGER DEFAULT 0,
    views INTEGER DEFAULT 0,
    status INTEGER DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);
"""

CREATE_COMMENT_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS comments (
    id VARCHAR(64) PRIMARY KEY,
    post_id VARCHAR(64) NOT NULL,
    user_id VARCHAR(64) NOT NULL,
    content TEXT NOT NULL,
    parent_id VARCHAR(64) DEFAULT NULL,
    likes INTEGER DEFAULT 0,
    status INTEGER DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (post_id) REFERENCES posts(id) ON DELETE CASCADE,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (parent_id) REFERENCES comments(id) ON DELETE CASCADE
);
"""

CREATE_WORLD_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS world (
    id SERIAL PRIMARY KEY,
    sender_id VARCHAR(64) NOT NULL,
    sender_name VARCHAR(255) NOT NULL,
    content TEXT NOT NULL,
    parent_id INTEGER DEFAULT NULL,
    created_at TIMESTAMP DEFAULT NOW(),
    FOREIGN KEY (sender_id) REFERENCES users(id) ON DELETE CASCADE
);
"""

CREATE_POST_LIKES_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS post_likes (
    id SERIAL PRIMARY KEY,
    post_id VARCHAR(64) NOT NULL,
    user_id VARCHAR(64) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(post_id, user_id),
    FOREIGN KEY (post_id) REFERENCES posts(id) ON DELETE CASCADE,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);
"""

CREATE_POST_FAVORITES_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS post_favorites (
    id SERIAL PRIMARY KEY,
    post_id VARCHAR(64) NOT NULL,
    user_id VARCHAR(64) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(post_id, user_id),
    FOREIGN KEY (post_id) REFERENCES posts(id) ON DELETE CASCADE,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);
"""

CREATE_USER_FOLLOWS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS user_follows (
    id SERIAL PRIMARY KEY,
    follower_id VARCHAR(64) NOT NULL,
    following_id VARCHAR(64) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(follower_id, following_id),
    FOREIGN KEY (follower_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (following_id) REFERENCES users(id) ON DELETE CASCADE
);
"""

CREATE_VERIFY_TOKENS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS verify_tokens (
    id SERIAL PRIMARY KEY,
    user_id VARCHAR(64) NOT NULL,
    token VARCHAR(255) NOT NULL UNIQUE,
    token_type VARCHAR(32) NOT NULL,
    expires_at TIMESTAMP NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);
"""

CREATE_POST_REPORTS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS post_reports (
    id SERIAL PRIMARY KEY,
    post_id VARCHAR(64) NOT NULL,
    reporter_id VARCHAR(64) NOT NULL,
    reason VARCHAR(64) NOT NULL,
    detail TEXT DEFAULT '',
    status INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (post_id) REFERENCES posts(id) ON DELETE CASCADE,
    FOREIGN KEY (reporter_id) REFERENCES users(id) ON DELETE CASCADE
);
"""

CREATE_BUG_REPORTS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS bug_reports (
    id SERIAL PRIMARY KEY,
    title VARCHAR(200) NOT NULL,
    detail TEXT NOT NULL,
    steps TEXT DEFAULT '',
    contact VARCHAR(200) DEFAULT '',
    reporter_id VARCHAR(64) DEFAULT NULL,
    reporter_name VARCHAR(64) DEFAULT '',
    user_agent TEXT DEFAULT '',
    page_url TEXT DEFAULT '',
    status INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (reporter_id) REFERENCES users(id) ON DELETE SET NULL
);
"""

CREATE_VERIFY_CODES_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS verify_codes (
    id SERIAL PRIMARY KEY,
    email VARCHAR(255) NOT NULL,
    code VARCHAR(6) NOT NULL,
    purpose VARCHAR(32) NOT NULL,
    expires_at TIMESTAMP NOT NULL,
    used INTEGER DEFAULT 0,
    attempts INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""

CREATE_INDEX_SQLS = [
    # pg_trgm 扩展：为 ILIKE '%关键词%' 模糊搜索提供 GIN 索引加速
    "CREATE EXTENSION IF NOT EXISTS pg_trgm;",
    # 基础 B-tree 索引
    "CREATE INDEX IF NOT EXISTS idx_posts_user_id ON posts(user_id);",
    "CREATE INDEX IF NOT EXISTS idx_posts_created_at ON posts(created_at DESC);",
    # 复合索引：加速列表查询（按状态+时间排序）与用户帖子查询
    "CREATE INDEX IF NOT EXISTS idx_posts_status_created ON posts(status, created_at DESC);",
    "CREATE INDEX IF NOT EXISTS idx_posts_user_status ON posts(user_id, status, created_at DESC);",
    "CREATE INDEX IF NOT EXISTS idx_comments_post_id ON comments(post_id);",
    "CREATE INDEX IF NOT EXISTS idx_world_created_at ON world(created_at DESC);",
    "CREATE INDEX IF NOT EXISTS idx_post_likes_post_id ON post_likes(post_id);",
    "CREATE INDEX IF NOT EXISTS idx_post_likes_user_id ON post_likes(user_id);",
    "CREATE INDEX IF NOT EXISTS idx_post_favorites_user_id ON post_favorites(user_id);",
    "CREATE INDEX IF NOT EXISTS idx_user_follows_follower ON user_follows(follower_id);",
    "CREATE INDEX IF NOT EXISTS idx_user_follows_following ON user_follows(following_id);",
    "CREATE INDEX IF NOT EXISTS idx_post_reports_post_id ON post_reports(post_id);",
    "CREATE INDEX IF NOT EXISTS idx_bug_reports_created_at ON bug_reports(created_at DESC);",
    "CREATE INDEX IF NOT EXISTS idx_bug_reports_status ON bug_reports(status);",
    "CREATE INDEX IF NOT EXISTS idx_verify_codes_email_purpose ON verify_codes(email, purpose);",
    "CREATE INDEX IF NOT EXISTS idx_verify_codes_expires ON verify_codes(expires_at);",
    # GIN 三元组索引：让 ILIKE 模糊搜索走索引而非全表扫描
    "CREATE INDEX IF NOT EXISTS idx_posts_title_trgm ON posts USING gin (title gin_trgm_ops);",
    "CREATE INDEX IF NOT EXISTS idx_posts_content_trgm ON posts USING gin (content gin_trgm_ops);",
    "CREATE INDEX IF NOT EXISTS idx_posts_category_trgm ON posts USING gin (category gin_trgm_ops);",
    "CREATE INDEX IF NOT EXISTS idx_users_name_trgm ON users USING gin (name gin_trgm_ops);",
    "CREATE INDEX IF NOT EXISTS idx_users_prefix_trgm ON users USING gin (prefix gin_trgm_ops);",
    "CREATE INDEX IF NOT EXISTS idx_users_intro_trgm ON users USING gin (intro gin_trgm_ops);",
]

# 全部建表语句集合
ALL_TABLE_SQL = [
    CREATE_USER_TABLE_SQL,
    CREATE_POST_TABLE_SQL,
    CREATE_COMMENT_TABLE_SQL,
    CREATE_WORLD_TABLE_SQL,
    CREATE_POST_LIKES_TABLE_SQL,
    CREATE_POST_FAVORITES_TABLE_SQL,
    CREATE_USER_FOLLOWS_TABLE_SQL,
    CREATE_VERIFY_TOKENS_TABLE_SQL,
    CREATE_POST_REPORTS_TABLE_SQL,
    CREATE_BUG_REPORTS_TABLE_SQL,
    CREATE_VERIFY_CODES_TABLE_SQL,
    *CREATE_INDEX_SQLS
]

# ──────────────────────────────────────────────────────────────
# 加密字典（按项目约束，所有加密相关字典放这里）
# 暂时留空结构，文本彩蛋混淆功能日后再启用
# ──────────────────────────────────────────────────────────────
AUTH_SALT = "fairy-forum-auth-salt-2026"
AUTH_NUM_REPLACEMENTS: dict = {}
AUTH_LETTER_VERSIONS: list = []
AUTH_SYMBOL_VERSIONS: list = []
AUTH_COMBINING_SETS: list = []
AUTH_ZW_SETS: list = []
AUTH_PADDING_SETS: list = []
AUTH_LIST_FOR_1: list = []

# ── 允许的用户查找键（预留） ──
allowed_search_keys = ['id', 'name', 'email']

# ──────────────────────────────────────────────────────────────
# Token / Cookie 配置
# 仅使用两个 Cookie：token 与 ID
# ──────────────────────────────────────────────────────────────
TOKEN_TTL_SECONDS = 7 * 24 * 3600   # Token 有效期：7 天
TOKEN_COOKIE_NAME = "token"         # Cookie 名：登录完整 token
ID_COOKIE_NAME = "ID"               # Cookie 名：用户 ID
COOKIE_PATH = "/"
COOKIE_DOMAIN = None                # None = 当前域名自动匹配
COOKIE_HTTPONLY = True              # 防 XSS 读取
COOKIE_SECURE = False               # 生产 HTTPS 环境改为 True
COOKIE_SAMESITE = "Lax"

# ──────────────────────────────────────────────────────────────
# 静态资源缓存版本号
# 浏览器对 JS/CSS/LPK 等强缓存 7 天（app.SEND_FILE_MAX_AGE_DEFAULT）。
# 每次更新静态资源（AfterBody.js / main.css 等）后，把此版本号 +1，
# 模板中 ?v= 自动变化即可让浏览器重新拉取，避免用户拿到旧文件。
# ──────────────────────────────────────────────────────────────
STATIC_VERSION = "8"

# ──────────────────────────────────────────────────────────────
# 用户注册默认值
# ──────────────────────────────────────────────────────────────
USER_ID_PREFIX = "RL"  # 新注册用户 ID 前缀（与旧库一致）
ALLOWED_USER_PREFIXES = ["HG", "YJ", "RL"]  # 仅允许这三种 ID 前缀
vip = "0"
DEFAULT_AVATARS = [
    "/static/img/avatars/LaoJun.png",
    "/static/img/avatars/LuoXiaoHei1.png",
    "/static/img/avatars/LuoXiaoHei2.png",
    "/static/img/avatars/MuXiZi.png",
]
# ──────────────────────────────────────────────────────────────
# 业务模块配置（forum-new 全量 API）
# ──────────────────────────────────────────────────────────────

# ID 前缀
POST_ID_PREFIX = "PS"
COMMENT_ID_PREFIX = "CM"

# ── SMTP 邮件（邮箱验证 / 找回密码）──
# 邮件里所有按钮 / 链接都使用固定域名，避免用 request.host_url 动态解析当前网址
SITE_BASE_URL = os.getenv("SITE_BASE_URL", "https://yjlt.top")
SMTP_HOST = os.getenv("SMTP_HOST", "smtpdm.aliyun.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "465"))
SMTP_USER = os.getenv("SMTP_USER", "maomi@email.yjlt.top")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
SMTP_FROM_NAME = os.getenv("SMTP_FROM_NAME", "妖精论坛(二创)")
RECEIVERALL = os.getenv("RECEIVERALL", SMTP_USER)

# ── Cloudflare Images（头像上传）──
# 对应 .env 中的 avatar_STORE_ID / avatar_READ_WRITE_TOKEN / avatar_WEBHOOK_PUBLIC_KEY
CF_IMAGES_ACCOUNT_ID = os.getenv("avatar_STORE_ID", "")
CF_IMAGES_API_TOKEN = os.getenv("avatar_READ_WRITE_TOKEN", "")
CF_IMAGES_WEBHOOK_PUBLIC_KEY = os.getenv("avatar_WEBHOOK_PUBLIC_KEY", "")
CF_IMAGES_DELIVERY_HOST = os.getenv("avatar_DELIVERY_HOST", "https://imagedelivery.net")

# 头像上传：保存到本地目录，通过 /avatar/<file> 静态路由访问（与 v1 一致）
# 不用 Cloudflare Images API（store_xxx 是交付 hash，不是 Account ID，无法路由到 /images/v1）
AVATAR_UPLOAD_DIR = os.getenv("AVATAR_UPLOAD_DIR", "/root/db/avatar")

# ── 帖子分类白名单（非法分类回落 general）──
ALLOWED_CATEGORIES = ["general", "叶羽", "创意", "求助"]

# ── 头像上传限制 ──
AVATAR_MAX_BYTES = 5 * 1024 * 1024  # 5MB

# ── 邮箱验证 token 有效期（分钟）──
VERIFY_TOKEN_EXPIRES_MINUTES = 30
