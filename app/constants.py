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
APP_VERSION = "1.2.4"
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

# ────────────────────────── 客户端发布 / 更新 ──────────────────────────

APP_RELEASES_API = "/api/app/releases"   # 发布清单接口（服务端 api/release）
APP_CHECK_API = "/api/app/check"         # 版本校验接口
APP_DOWNLOAD_PAGE = "/Download"          # 官网发布 / 下载页

# ────────────────────────── 远端静态资源（按需下载 + 本地缓存）──────────────────────────

REMOTE_LPK = "/static/live2d/HEI.lpk"   # 4.0 的历史直链（兼容旧客户端与旧缓存）

# ── Live2D 桌宠模型版本 ──
# 模型包统一托管在服务端 /static/live2d/ 下，客户端按需下载 + 本地缓存
# （延续「不内置模型」原则；见 app/live2d/provider.py）。
#   key       版本号（配置文件 pet.model 的取值，如 "4.0"）
#   label     界面展示名
#   name      归一化后的模型名（目录名 / .model3.json 前缀，如 "HEI4.0"）
#   lpk_name  本地缓存文件名（4.0 沿用 "HEI.lpk"，以便复用已有缓存）
#   remotes   远端直链（按顺序尝试；首个为主链接，其余为回退）
#   size      LPK 字节数（0 表示未知）
#   sha256    LPK 的 sha256（小写十六进制；空串表示未记录）
#   note      设置页展示的简短说明
LIVE2D_MODEL_DEFAULT = "4.0"

LIVE2D_MODELS = (
    {
        "key": "1.1", "label": "1.1", "name": "HEI1.1",
        "lpk_name": "HEI1.1.lpk",
        "remotes": ("/static/live2d/HEI11.lpk",),
        "size": 1831276,
        "sha256": "6dcb2d0f8513ad41fe68c6471b711d71f1e14a09c9e6b383e729d5e9c5576c1c",
        "note": "最初版本",
    },
    {
        "key": "2.3", "label": "2.3", "name": "HEI2.3",
        "lpk_name": "HEI2.3.lpk",
        "remotes": ("/static/live2d/HEI23.lpk",),
        "size": 1913996,
        "sha256": "c87da38fe958831995873b5852f5058671b50d69bf2d5a0cf715cfd8ca06a417",
        "note": "第二代模型",
    },
    {
        "key": "3.0.1", "label": "3.0.1", "name": "HEI3.0.1",
        "lpk_name": "HEI3.0.1.lpk",
        "remotes": ("/static/live2d/HEI301.lpk",),
        "size": 1985322,
        "sha256": "519f112eb5d4c49161b79717f1c4b740066b3a3ce5e4cd4fd7b57f8b6ae0266d",
        "note": "第三代模型",
    },
    {
        "key": "3.0.2", "label": "3.0.2", "name": "HEI3.0.2",
        "lpk_name": "HEI3.0.2.lpk",
        "remotes": ("/static/live2d/HEI302.lpk",),
        "size": 1991554,
        "sha256": "cd54b7030e8604d0ed6e38c63d085206c8b70e56a0bb1f74d6fbffe3d6ece737",
        "note": "第三代修订",
    },
    {
        "key": "4.0", "label": "4.0", "name": "HEI4.0",
        "lpk_name": "HEI.lpk",
        "remotes": ("/static/live2d/HEI40.lpk", "/static/live2d/HEI.lpk"),
        "size": 2077164,
        "sha256": "49704e688db0d031297e433c5de7c9d76509a5a2d65f19f15548c25fb5a856c2",
        "note": "当前默认版本",
    },
)


def _normalize_model_key(value) -> str:
    """把任意写法（``"4.0"`` / ``"HEI4.0"`` / ``"hei40"``）归一化为版本号。"""
    text = str(value or "").strip()
    if not text:
        return LIVE2D_MODEL_DEFAULT
    low = text.lower().replace("_", "").replace("-", "").replace(" ", "")
    for spec in LIVE2D_MODELS:
        key = spec["key"]
        name = spec["name"].lower()
        if low in (key, name, name.replace(".", ""),
                   "hei" + key, "hei" + key.replace(".", "")):
            return key
    if low.startswith("hei"):
        tail = low[3:]
        for spec in LIVE2D_MODELS:
            if tail in (spec["key"], spec["key"].replace(".", "")):
                return spec["key"]
    return LIVE2D_MODEL_DEFAULT


def live2d_model(key=None) -> dict:
    """返回某个模型版本的元数据；未知取值一律回退到默认版本。"""
    target = _normalize_model_key(key)
    for spec in LIVE2D_MODELS:
        if spec["key"] == target:
            return spec
    return LIVE2D_MODELS[-1]


def live2d_model_choices() -> tuple:
    """``((版本号, 展示名), ...)``，供设置页 / 右键菜单渲染。"""
    return tuple((spec["key"], spec["label"]) for spec in LIVE2D_MODELS)


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
# 随包发布的可信根证书（打包环境里 certifi 自带的可能是旧版，见 app/tls.py）
RES_CA_BUNDLE = resource("ca", "cacert.pem")

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

# 应用内指针尺寸系数（倍数）。基准边长见 app/cursors.BASE_TARGET_PX。
CURSOR_SCALE_MIN = 0.5
CURSOR_SCALE_MAX = 2.0
CURSOR_SCALE_DEFAULT = 1.0

SYSTEM_CURSOR_DIR_NAME = "Cursors\\罗小黑鼠标指针"
SYSTEM_CURSOR_SCHEME = "罗小黑鼠标指针"

URI_SCHEME = "Crforum"
URI_SCHEME_DISPLAY = "Crforum://"

# 本地数据目录（供“打开数据目录”入口使用）
DATA_DIR = data_dir
