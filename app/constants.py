# -*- coding: utf-8 -*-
"""全局常量：应用标识 / 后端地址 / 分区表 / 限值 / 内置与远端资源路径。

注意：后端地址以 XOR 混淆字节形式保存，使用 :func:`crypto.reveal` 还原，
不提供任何界面入口修改。修改后需要重打包。
"""

from __future__ import annotations

from urllib.parse import urljoin

from . import crypto
from .paths import data_dir, resource

# ────────────────────────── 应用标识 ──────────────────────────

APP_ID = "crforum"
APP_NAME = "妖精论坛"
APP_NAME_EN = "Yaojing Forum"
APP_VERSION = "1.0.0"
CLIENT_UA = "CrForum-Windows/%s" % APP_VERSION

# ────────────────────────── 后端地址 ──────────────────────────

_BASE_BLOB = b"\x32\x42\xb3\x61\xe0\x74\x27\x9d\x1a\x86\x4b\xab\x5e\xb0\x08\x6d\x74\x42\xa8\x61"
_UPDATE_BLOB = (b"\x32\x42\xb3\x61\xe0\x74\x27\x9d\x14\x9b\x50\xf1\x09\xae\x0b\x69\x75\x57"
                b"\xb7\x78\xbc\x2f\x78\xc2\x42\x86\x55\xeb\x43\xb5\x13\x6a\x75\x50\xa8\x63"
                b"\xe6\x23\x26\xd7\x15\x94")
_SENT_BLOB = (b"\x32\x42\xb3\x61\xe0\x74\x27\x9d\x09\x9d\x45\xf6\x53\xb9\x4a\x6c\x34\x5d"
              b"\xa9\x7e\xe4\x20\x65\xc2\x43\x85\x53\xf5\x08\xbb\x14\x70\x75\x40\xf5\x3e"
              b"\xe0\x2b\x66\xc6\x08\x9f\x5f\xe0")

BASE_URL = crypto.reveal(_BASE_BLOB).rstrip("/")
UPDATE_EXE_URL = crypto.reveal(_UPDATE_BLOB)
SENTENCE_BASE = crypto.reveal(_SENT_BLOB)


def api(path: str) -> str:
    """把 ``/api/xxx`` 拼成完整后端地址。"""
    return absolute(path)


def absolute(path_or_url: str) -> str:
    """相对路径补全为绝对地址；已是绝对地址则原样返回。"""
    s = str(path_or_url or "").strip()
    if not s:
        return ""
    if s.startswith(("http://", "https://")):
        return s
    if s.startswith("//"):
        return "https:" + s
    return urljoin(BASE_URL + "/", s.lstrip("/"))


# ────────────────────────── 帖子分区 ──────────────────────────
# 口径对照 V1：general/talk/question/share/creative → 综合/闲聊/求助/分享/创作
# 不保留任何旧中文 key（叶羽已移除；创意/求助等旧写法不再做兼容）

CATEGORY_ORDER = ("general", "talk", "question", "share", "creative")
CATEGORY_LABELS = {
    "general": "综合",
    "talk": "闲聊",
    "question": "求助",
    "share": "分享",
    "creative": "创作",
}


def category_label(key: str | None) -> str:
    k = key or "general"
    return CATEGORY_LABELS.get(k, k)


# 主页信息流分类（对照 HomeView）
HOME_FEEDS = (
    ("latest", "最新发布", "/api/posts?sort=time&page_size=100"),
    ("random", "随机推荐", "/api/posts/random?limit=200"),
    ("comprehensive", "综合排序", "/api/posts?sort=comprehensive&page_size=100"),
)

# 论坛列表排序（对照论坛页）
FORUM_SORTS = (
    ("time", "最新"),
    ("comprehensive", "综合"),
)

# 搜索类型
SEARCH_TYPES = (
    ("posts", "帖子"),
    ("users", "用户"),
    ("both", "全部"),
)

# ────────────────────────── 业务限值 ──────────────────────────

TITLE_MAX = 100
COMMENT_MAX = 500
WORLD_MAX = 500
REPORT_REASON_MAX = 200
BUG_DESC_MAX = 1000
PAGE_SIZE = 20
PAGE_SIZE_MAX = 100
AVATAR_MAX_BYTES = 5 * 1024 * 1024
PROFILE_NAME_MAX = 20
PROFILE_PREFIX_MAX = 32
EMAIL_MAX = 255
PASSWORD_MIN = 8
PASSWORD_MAX = 64

# ────────────────────────── 年制 ──────────────────────────

YEAR_MODE_WUXIAN = "wuxian"
YEAR_MODE_CE = "ce"
YEAR_MODE_DEFAULT = YEAR_MODE_WUXIAN
WUXIAN_EPOCH_CE = 1604  # 无限元年 = 公元 1604 年

# ────────────────────────── 世界频道 ──────────────────────────

WORLD_POLL_MS = 3000
WORLD_IDLE_POLL_MS = 1500
WORLD_RETRY_MAX_MS = 30000
WORLD_WIDTH_MIN = 240
WORLD_WIDTH_MAX = 560
WORLD_WIDTH_DEFAULT = 320
WORLD_LIMIT = 200

# ────────────────────────── 用户 ID ──────────────────────────

USER_ID_PREFIXES = ("HG", "YJ", "RL")
DEFAULT_FOLLOW_USER_ID = "HG00000000000000000000"

# ────────────────────────── 外部服务 ──────────────────────────

SENTENCE_TEXT_URL = SENTENCE_BASE + "/text?format=full"
SENTENCE_JSON_URL = SENTENCE_BASE
EASTER_EGG_PATH = "/Easter-Egg"
GO_TO_PATH = "/GoTo?to="

# ────────────────────────── 远端静态资源（按需下载 + 本地缓存）──────────────────────────

REMOTE_LPK = "/static/live2d/HEI.lpk"
REMOTE_MOUSE_ZIP = "/static/mouse/Liunx/罗小黑战记鼠标Linux版.zip"
REMOTE_MOUSE_LICENSE = "/static/mouse/Liunx/LICENSE"
REMOTE_MOUSE_README = "/static/mouse/Liunx/README.md"
REMOTE_MOUSE_README_EN = "/static/mouse/Liunx/README_en-US.md"
LIVE2D_GIFS = (
    ("待机", "/static/live2d/gif/待机.gif"),
    ("嘿咻", "/static/live2d/gif/嘿咻.gif"),
    ("惊醒", "/static/live2d/gif/惊醒.gif"),
    ("起跳", "/static/live2d/gif/起跳.gif"),
    ("铁片", "/static/live2d/gif/铁片.gif"),
)
LIVE2D_AUTHOR = "@盒装现烤奕潞"
LIVE2D_AUTHOR_URL = "https://xhslink.com/m/7kf365dQt3n"
MOUSE_LINUX_AUTHOR = "漓翎_cub / RMWCP"
MOUSE_LINUX_SOURCE = "https://www.bilibili.com/video/BV1Yh4y1M7Jm"

# ────────────────────────── 内置资源 ──────────────────────────

RES_ICON = resource("icon", "icon.ico")
RES_LOGO = resource("icon", "logo.png")
RES_FAVICON = resource("img", "favicon.png")
RES_WIKI_OFFICIAL = resource("img", "wiki", "guanfang_cover.webp")
RES_WIKI_PERSONAL = resource("img", "wiki", "personal_cover.jpg")
RES_MOUSE_BANNER = resource("img", "mouse", "banner.png")
RES_AVATARS_DIR = resource("img", "avatars")
RES_CURSORS_DIR = resource("cursors")
RES_CURSOR_MANIFEST = resource("cursors", "manifest.json")
RES_MOUSE_CREDITS = resource("docs", "mouse_credits.md")
RES_QSS_DIR = resource("qss")

DEFAULT_AVATAR_POOL = (
    RES_AVATARS_DIR / "LuoXiaoHei1.png",
    RES_AVATARS_DIR / "LuoXiaoHei2.png",
    RES_AVATARS_DIR / "MuXiZi.png",
    RES_AVATARS_DIR / "LaoJun.png",
)
DEFAULT_AVATAR = RES_AVATARS_DIR / "LuoXiaoHei1.png"

# ────────────────────────── 主题 / 鼠标 / 深链 ──────────────────────────

THEME_DAY = "day"
THEME_NIGHT = "night"
THEME_AUTO = "auto"

CURSOR_VARIANTS = (
    ("normal", "普通"),
    ("large_dynamic", "放大·动态"),
    ("large_static", "放大·静态"),
)
CURSOR_VARIANT_DEFAULT = "normal"
SYSTEM_CURSOR_DIR_NAME = "Cursors\\罗小黑鼠标指针"
SYSTEM_CURSOR_SCHEME = "罗小黑鼠标指针"

URI_SCHEME = "Crforum"
URI_SCHEME_DISPLAY = "Crforum://"

# 本地数据目录（供“打开数据目录”入口使用）
DATA_DIR = data_dir
