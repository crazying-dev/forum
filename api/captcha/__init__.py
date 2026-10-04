"""人机验证中央入口：Cloudflare Turnstile（默认）/ 自研滑块（兜底）/ 关闭。

Provider（config.CAPTCHA_PROVIDER）
----------------------------------
* ``turnstile``（默认）：Cloudflare Turnstile，服务端调 siteverify 校验，
  实现见 ``api/turnstile.py``；**sitekey/secret 未配置时自动回退 slider**，
  避免改了默认值却忘记配密钥把线上打死。
* ``slider``：本文件内的自研滑块拼图（无第三方依赖 / 无需外网，国内可用）。
* ``off``：一律放行（等价于 CAPTCHA_ENABLED=0）。

客户端统一契约
--------------
* ``POST /api/captcha/challenge`` 返回 ``provider`` 字段告知用哪种方式；
  turnstile 时额外返回 ``sitekey`` / ``embed_url``（WebView 承载页地址）；
* 客户端把凭据**统一放进 ``captcha_token`` 字段**提交业务请求 —— 因此
  ``@captcha_required`` 与 11 个受保护接口零改动；
* ``POST /api/captcha/verify`` 仅 slider 需要（两步式预校验）；Turnstile 的
  token 一次性（Cloudflare 规定），必须留给业务请求消费，故此处只透传；
* ``GET /captcha-embed``：给 Windows(QWebEngineView) / Android(WebView) 用的
  承载页，加载 Turnstile 组件并把 token 回传宿主。

自研滑块（slider）设计
----------------------
* 服务端内存字典存答案：{token: {answer_x, ip, expires, solved}}，与
  api/ratelimit.py 同一风格（模块级 threading.Lock + dict），重启即丢；
* 一次性 token：业务请求校验时 pop 掉，杜绝重放；
* TTL 默认 5 分钟；绑定客户端 IP；水平容差默认 ±12px（放宽以适配触屏）。

接口
----
    POST /api/captcha/challenge   生成挑战（下发 provider 配置）
    POST /api/captcha/verify      校验滑块位置（仅 slider）
    GET  /captcha-embed           WebView 承载页（仅 turnstile）

业务端接入
----------
在需要的接口上加装饰器 ``@captcha_required`` 即可；服务端由此调用
``verify_captcha(payload)`` 完成校验（provider=off 时整体放行）。
"""
from __future__ import annotations

import base64
import io
import random
import secrets
import threading
import time
from functools import wraps

from flask import Blueprint, jsonify, render_template, request

import config
from api.ratelimit import rate_limit
from api.turnstile import (
    TOKEN_FIELD,
    configured as turnstile_configured,
    sitekey as turnstile_sitekey,
    verify_token as turnstile_verify,
)

captcha_bp = Blueprint("captcha", __name__)

# WebView 承载页（Windows QWebEngineView / Android WebView）
captcha_embed_bp = Blueprint("captcha_embed", __name__)
CAPTCHA_EMBED_PATH = "/captcha-embed"

# 挑战 token 状态：{token: {"answer_x": int, "ip": str, "expires": float, "solved": bool}}
_lock = threading.Lock()
_store: dict = {}

# 校验失败时统一的错误码：客户端据此「刷新挑战 + 重新弹出滑块」
CAPTCHA_REQUIRED_CODE = "CAPTCHA_REQUIRED"


# ──────────────────────────────────────────────
# 工具：真实客户端 IP（与 api/ratelimit.py 口径一致）
# ──────────────────────────────────────────────
def _client_ip() -> str:
    forwarded = request.headers.get("X-Forwarded-For", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.remote_addr or "0.0.0.0"


def _provider(force: str = "") -> str:
    """当前生效的人机验证 provider：turnstile / slider / off。

    ``force="slider"`` 时强制走自研滑块——这是客户端在 Turnstile 解不出来
    （组件报错 / 加载超时）时的回退通道；服务端已关闭验证（off）时 force
    无效，仍返回 off（不会把已关掉的验证又打开）。
    """
    if not getattr(config, "CAPTCHA_ENABLED", True):
        return "off"
    raw = str(getattr(config, "CAPTCHA_PROVIDER", "turnstile") or "").strip().lower()
    if raw in ("off", "none", "disable", "disabled", "0", "false"):
        return "off"
    if str(force or "").strip().lower() == "slider":
        return "slider"
    if raw == "slider":
        return "slider"
    # 其余（含默认 turnstile）：密钥不齐则回退自研滑块，绝不让线上裸奔
    if turnstile_configured():
        return "turnstile"
    return "slider"


def _ttl() -> int:
    try:
        value = int(getattr(config, "CAPTCHA_TTL_SECONDS", 300))
    except (TypeError, ValueError):
        value = 300
    return value if value > 0 else 300


def _tolerance() -> int:
    try:
        value = int(getattr(config, "CAPTCHA_TOLERANCE", 12))
    except (TypeError, ValueError):
        value = 12
    return value if value >= 0 else 12


# ──────────────────────────────────────────────
# 图像生成（Pillow）：随机纹理背景 + 从背景裁出的拼图块
# ──────────────────────────────────────────────
def _rand_color(low: int = 0, high: int = 255):
    return (random.randint(low, high), random.randint(low, high), random.randint(low, high))


def _make_background(width: int, height: int):
    """随机彩色背景：渐变底色 + 若干半透明色块 + 干扰线 + 噪点。"""
    from PIL import Image, ImageDraw

    base = _rand_color(40, 220)
    img = Image.new("RGB", (width, height), base)
    d = ImageDraw.Draw(img, "RGBA")
    # 半透明色块（椭圆），增加纹理复杂度
    for _ in range(random.randint(6, 10)):
        x0 = random.randint(-width // 3, width)
        y0 = random.randint(-height // 3, height)
        w = random.randint(width // 5, int(width * 0.6))
        h = random.randint(height // 5, int(height * 0.6))
        color = (_rand_color(), random.randint(50, 130))
        d.ellipse([x0, y0, x0 + w, y0 + h], fill=(color[0][0], color[0][1], color[0][2], color[1]))
    # 干扰线
    for _ in range(random.randint(8, 14)):
        x0, y0 = random.randint(0, width), random.randint(0, height)
        x1, y1 = random.randint(0, width), random.randint(0, height)
        c = _rand_color()
        d.line([x0, y0, x1, y1], fill=(c[0], c[1], c[2], random.randint(70, 150)),
               width=random.randint(1, 2))
    # 噪点（对抗纯色 / 边缘检测）
    for _ in range(max(1, width * height // 40)):
        x = random.randint(0, width - 1)
        y = random.randint(0, height - 1)
        c = random.randint(0, 255)
        img.putpixel((x, y), (c, c, c))
    return img


def _piece_mask(size: int):
    """拼图块形状遮罩（L 模式）：圆角方块 + 上凸 / 右凸两个圆形，做出拼图手感。"""
    from PIL import Image, ImageDraw

    scale = 4  # 超采样后缩放，得到平滑边缘
    s = size * scale
    mask = Image.new("L", (s, s), 0)
    d = ImageDraw.Draw(mask)
    d.rounded_rectangle([0, 0, s - 1, s - 1], radius=s // 6, fill=255)
    knob = s // 5
    cx = s // 2
    d.ellipse([cx - knob, -knob, cx + knob, knob], fill=255)          # 上凸
    cy = s // 2
    d.ellipse([s - knob, cy - knob, s + knob, cy + knob], fill=255)    # 右凸
    return mask.resize((size, size), Image.LANCZOS)


def _edge_image(mask):
    """由遮罩求边缘（用于给拼图块 / 缺口描边）。"""
    from PIL import ImageFilter

    edges = mask.filter(ImageFilter.FIND_EDGES)
    return edges.point(lambda v: 255 if v > 30 else 0)


def _render_challenge():
    """渲染一帧挑战，返回 (背景图, 拼图块, answer_x, piece_y, width, height, piece)。"""
    from PIL import Image

    width = int(getattr(config, "CAPTCHA_WIDTH", 320))
    height = int(getattr(config, "CAPTCHA_HEIGHT", 180))
    piece = int(getattr(config, "CAPTCHA_PIECE", 50))
    margin = 8

    bg = _make_background(width, height)
    mask = _piece_mask(piece)

    # 缺口水平位置：留出足够拖动距离（不贴着左端），且完整落在图内
    lo = min(piece + 20, max(0, width - piece - margin - 1))
    hi = max(lo, width - piece - margin)
    answer_x = random.randint(lo, hi)
    piece_y = random.randint(10, max(10, height - piece - 10))

    region = bg.crop((answer_x, piece_y, answer_x + piece, piece_y + piece))
    piece_img = region.convert("RGBA")
    piece_img.putalpha(mask)
    # 拼图块描边（浅白），提升可辨识度
    edges = _edge_image(mask)
    stroke = Image.new("RGBA", (piece, piece), (255, 255, 255, 150))
    piece_img.paste(stroke, (0, 0), edges)

    # 背景挖缺口：半透明黑影 + 白色描边
    bg_rgba = bg.convert("RGBA")
    hole = Image.new("RGBA", (piece, piece), (0, 0, 0, 150))
    bg_rgba.paste(hole, (answer_x, piece_y), mask)
    bg_rgba.paste(Image.new("RGBA", (piece, piece), (255, 255, 255, 90)), (answer_x, piece_y), edges)

    return bg_rgba.convert("RGB"), piece_img, answer_x, piece_y, width, height, piece


def _data_url(img) -> str:
    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode("ascii")


# ──────────────────────────────────────────────
# token 存取
# ──────────────────────────────────────────────
def _prune_locked(now: float) -> None:
    """清理过期 / 已消费的记录（调用方需已持有 _lock）。"""
    stale = [k for k, v in _store.items() if v.get("expires", 0) < now]
    for k in stale:
        _store.pop(k, None)
    # 容量上限：超限时优先淘汰最早过期的记录
    limit = int(getattr(config, "CAPTCHA_MAX_TOKENS", 5000) or 5000)
    if limit > 0 and len(_store) > limit:
        for k, _ in sorted(_store.items(), key=lambda kv: kv[1].get("expires", 0)):
            if len(_store) <= limit:
                break
            _store.pop(k, None)


def create_challenge() -> dict:
    """生成一次挑战并登记答案，返回可直接 jsonify 的负载。"""
    bg, piece_img, answer_x, piece_y, width, height, piece = _render_challenge()
    token = secrets.token_urlsafe(24)
    now = time.time()
    ttl = _ttl()
    with _lock:
        _prune_locked(now)
        _store[token] = {
            "answer_x": answer_x,
            "ip": _client_ip(),
            "expires": now + ttl,
            "solved": False,
        }
    return {
        "success": True,
        "token": token,
        "bg": _data_url(bg),
        "piece": _data_url(piece_img),
        "y": piece_y,
        "width": width,
        "height": height,
        "piece_size": piece,
        "expires_in": ttl,
    }


# ──────────────────────────────────────────────
# 校验
# ──────────────────────────────────────────────
def verify_slider(token: str, x) -> tuple[bool, str]:
    """校验滑块水平位置；通过则把该 token 标记为已解答（不消费）。

    返回 (ok, message)；失败时该 token 失效（一次性，防爆破）。
    """
    if not token:
        return False, "请先获取人机验证"
    now = time.time()
    with _lock:
        record = _store.get(token)
        if not record or record.get("expires", 0) < now:
            _store.pop(token, None)
            return False, "人机验证已过期，请重新验证"
        if record.get("ip") != _client_ip():
            _store.pop(token, None)
            return False, "人机验证失效，请重新验证"
        try:
            pos = float(x)
        except (TypeError, ValueError):
            _store.pop(token, None)
            return False, "人机验证失败，请重试"
        if abs(pos - float(record.get("answer_x", 0))) > _tolerance():
            _store.pop(token, None)
            return False, "人机验证失败，请重试"
        record["solved"] = True
    return True, ""


def _consume_slider(token: str, raw_x) -> tuple[bool, str]:
    """一次性消费滑块凭据（校验过期 / IP / 坐标）。"""
    now = time.time()
    with _lock:
        record = _store.pop(token, None)
    if not record:
        return False, "人机验证已过期，请重新验证"
    if record.get("expires", 0) < now:
        return False, "人机验证已过期，请重新验证"
    if record.get("ip") != _client_ip():
        return False, "人机验证失效，请重新验证"
    if raw_x is not None and raw_x != "":
        try:
            pos = float(raw_x)
        except (TypeError, ValueError):
            return False, "人机验证失败，请重试"
        if abs(pos - float(record.get("answer_x", 0))) > _tolerance():
            return False, "人机验证失败，请重试"
        return True, ""
    if record.get("solved"):
        return True, ""
    return False, "请先完成人机验证"


def verify_captcha(payload) -> tuple[bool, str]:
    """业务请求接入点：按凭据形态校验并消费一次性凭据。

    判定顺序（与全局 provider 解耦，兼容客户端回退）：

    1. token 命中服务端内存里的滑块凭据 → 按 slider 校验（支持
       ``{captcha_token, captcha_x}`` 一步式，或已 ``solved`` 的两步式）；
    2. 否则按全局 provider：turnstile → 交 siteverify；slider → 已过期。
    """
    if not getattr(config, "CAPTCHA_ENABLED", True):
        return True, ""
    data = payload if isinstance(payload, dict) else {}
    token = str(data.get(TOKEN_FIELD) or "").strip()
    if not token:
        return False, "请先完成人机验证"
    provider = _provider()
    if provider == "off":
        return True, ""
    with _lock:
        is_slider = token in _store
    if is_slider or provider == "slider":
        return _consume_slider(token, data.get("captcha_x"))
    return turnstile_verify(token, _client_ip())


def captcha_required(fn):
    """装饰器：为业务接口添加人机验证校验（失败返回 400 + code=CAPTCHA_REQUIRED）。

    建议放在 @login_required 之内（下方），让鉴权先于人机验证执行。
    """
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not getattr(config, "CAPTCHA_ENABLED", True):
            return fn(*args, **kwargs)
        payload = request.get_json(silent=True) or {}
        ok, msg = verify_captcha(payload)
        if not ok:
            return jsonify({"success": False, "code": CAPTCHA_REQUIRED_CODE,
                            "message": msg}), 400
        return fn(*args, **kwargs)
    return wrapper


# ──────────────────────────────────────────────
# 接口
# ──────────────────────────────────────────────
@captcha_bp.route("/challenge", methods=["POST"])
def api_captcha_challenge():
    """生成人机验证挑战（无需登录）；provider=slider 时才真正画图。

    ``?provider=slider`` 可强制下发自研滑块挑战——供客户端在 Turnstile
    解不出来时回退使用（不能覆盖服务端已关闭验证的状态）。
    """
    provider = _provider(request.args.get("provider"))
    if provider == "off":
        return jsonify({"success": True, "enabled": False, "token": ""}), 200
    if rate_limit("captcha", 60, 300):
        return jsonify({"success": False, "message": "请求过于频繁，请稍后再试"}), 429
    if provider == "turnstile":
        # Turnstile 的挑战由客户端 JS / WebView 承载页完成，服务端只下发配置
        return jsonify({
            "success": True,
            "enabled": True,
            "provider": "turnstile",
            "sitekey": turnstile_sitekey(),
            "embed_url": CAPTCHA_EMBED_PATH,
            "expires_in": 300,
        }), 200
    try:
        payload = create_challenge()
    except Exception as e:  # noqa: BLE001 — 图像生成异常不应 500
        print(f"[captcha] 生成挑战失败：{e}")
        return jsonify({"success": False, "message": "生成人机验证失败"}), 500
    payload["provider"] = "slider"
    return jsonify(payload), 200


@captcha_bp.route("/verify", methods=["POST"])
def api_captcha_verify():
    """两步式预校验（仅 slider）；turnstile 只透传 token。"""
    provider = _provider()
    if provider == "off":
        return jsonify({"success": True, "enabled": False}), 200
    data = request.get_json(silent=True) or {}
    token = str(data.get(TOKEN_FIELD) or "").strip()
    if not token:
        return jsonify({"success": False, "code": CAPTCHA_REQUIRED_CODE,
                        "message": "请先完成人机验证"}), 400
    with _lock:
        is_slider = token in _store
    if provider == "turnstile" and not is_slider:
        # Turnstile token 一次性：这里不能消费，必须留给业务请求去校验
        return jsonify({"success": True, "provider": "turnstile", "token": token,
                        "message": "请随业务请求提交该 token"}), 200
    ok, msg = verify_slider(token, data.get("captcha_x"))
    if not ok:
        return jsonify({"success": False, "code": CAPTCHA_REQUIRED_CODE,
                        "message": msg}), 400
    return jsonify({"success": True, "token": token, "message": "验证通过"}), 200


# ──────────────────────────────────────────────
# WebView 承载页（Windows QWebEngineView / Android WebView）
# ──────────────────────────────────────────────
@captcha_embed_bp.route(CAPTCHA_EMBED_PATH, methods=["GET"])
def captcha_embed_page():
    """加载 Turnstile 组件，并通过 JS bridge / document.title 把 token 回传宿主。

    query 参数：?theme=dark|light&lang=zh-cn&size=flexible|normal|compact
    """
    theme = "dark" if (request.args.get("theme") or "").strip().lower() == "dark" else "light"
    lang = (request.args.get("lang") or "zh-cn").strip() or "zh-cn"
    size = (request.args.get("size") or "normal").strip().lower()
    if size not in ("normal", "compact", "flexible"):
        size = "normal"
    provider = _provider()
    return render_template(
        "captcha_embed.html",
        provider=provider,
        sitekey=turnstile_sitekey() if provider == "turnstile" else "",
        theme=theme,
        lang=lang,
        size=size,
    )


__all__ = [
    "captcha_bp",
    "captcha_embed_bp",
    "CAPTCHA_EMBED_PATH",
    "captcha_required",
    "verify_captcha",
    "verify_slider",
    "create_challenge",
    "CAPTCHA_REQUIRED_CODE",
]
