"""页面路由：渲染前端模板。"""
import uuid

from flask import Blueprint, render_template, redirect, request, url_for, Response, jsonify

import db

pages_bp = Blueprint("pages", __name__)


@pages_bp.route("/")
def index():
    return render_template("index.html")


@pages_bp.route("/forum")
def forum():
    return render_template("forum.html")


@pages_bp.route("/post/create")
def post_create():
    return render_template("post_create.html")


@pages_bp.route("/post/<post_id>")
def post_detail(post_id):
    return render_template("post_detail.html", post_id=post_id)


@pages_bp.route("/auth")
def auth():
    """统一承载登录 / 注册 / 找回密码三种模式。

    mode 参数：login（默认）| register | reset
    """
    mode = (request.args.get("mode") or "login").strip().lower()
    if mode not in ("login", "register", "reset"):
        mode = "login"
    return render_template("auth.html", mode=mode, show_world=False)


@pages_bp.route("/login")
def login():
    return redirect(url_for("pages.auth", mode="login"))


@pages_bp.route("/register")
def register():
    return redirect(url_for("pages.auth", mode="register"))


@pages_bp.route("/reset-password")
def reset_password():
    """找回密码入口：邮件链接 ?token= 有效则跳转 auth 页设置新密码，无效则展示失败页。"""
    token = request.args.get("token") or ""
    if token:
        token_info = db.verify.get_verify_token(token, "password_reset")
        if not token_info:
            return render_template("verify_failed.html")
        target = url_for("pages.auth", mode="reset")
        target += ("&" if "?" in target else "?") + "token=" + token
        return redirect(target)
    return redirect(url_for("pages.auth", mode="reset"))


@pages_bp.route("/search")
def search():
    return render_template("search.html")


@pages_bp.route("/users/<user_id>")
def users(user_id):
    return render_template("users.html", user_id=user_id)


@pages_bp.route("/privacy")
def privacy():
    return render_template("privacy.html", show_world=False)


@pages_bp.route("/WIKI")
def wiki():
    return render_template("wiki.html")


@pages_bp.route("/WIKI/GuanFang")
def wiki_guanfang():
    return render_template("wiki_guanfang.html")


@pages_bp.route("/WIKI/Personal")
def wiki_personal():
    return render_template("wiki_personal.html")


@pages_bp.route("/WIKI/Personal/mouse")
def wiki_personal_mouse():
    return render_template("mouse.html")


@pages_bp.route("/WIKI/Personal/mouse/Liunx")
def wiki_personal_mouse_liunx():
    return render_template("mouse_liunx.html")


@pages_bp.route("/World")
def world_page():
    """世界频道独立页（全屏版）。"""
    return render_template("world_page.html", show_world=False)


@pages_bp.route("/QQ/redirect")
def qq_redirect():
    return redirect("https://qm.qq.com/q/bLxr68HnUI")


@pages_bp.route("/robots.txt")
def robots_txt():
    txt = (
        "User-agent: *\n"
        "Allow: /posts/*\n"
        "Allow: /users/*\n"
        "Disallow: /api/*\n"
    )
    return Response(txt, mimetype="text/plain")


@pages_bp.route("/INFO/")
@pages_bp.route("/INFO")
def info_easter_egg():
    """CORS 白名单接口：仅允许 men.umrca.com 跨域访问，返回彩蛋文案。"""
    resp = Response(_pick_info_text())
    resp.headers["Access-Control-Allow-Origin"] = "men.umrca.com"
    resp.headers["Access-Control-Allow-Methods"] = "GET, OPTIONS"
    resp.headers["Access-Control-Allow-Headers"] = "Content-Type"
    return resp


def _pick_info_text():
    import random
    return random.choice([
        "妖精论坛——一个充满神秘色彩的封闭区域，在此处，你会与聚灵而生的妖精，亦或者得到某种机遇而打开修行之路的人类，展开全新的相遇",
        "神秘的妖精论坛，等待有缘人的到来。",
    ])


@pages_bp.route("/TheDoorOfBings/UUID4/")
def the_door_of_bings_uuid():
    return jsonify([str(uuid.uuid4())])


@pages_bp.route("/WIKI/Personal/Live2D")
def wiki_personal_live2d():
    return redirect("/Live2D")


@pages_bp.route("/Live2D")
def live2d():
    return render_template("live2d.html", show_world=False, show_global_live2d=False)


@pages_bp.route("/verify-email")
def verify_email():
    """邮箱验证落地页：邮件中的链接点击后校验 token。

    有效 → 标记邮箱已验证并删除 token，展示成功页；
    无效/过期 → 展示失败页。
    """
    token = (request.args.get("token") or "").strip()
    if token:
        token_info = db.verify.get_verify_token(token, "email_verify")
        if token_info:
            db.verify.update_user_email_verified(token_info["user_id"])
            db.verify.delete_verify_token(token)
            return render_template("verify_success.html")
        return render_template("verify_failed.html")
    return redirect(url_for("pages.auth", mode="login"))


@pages_bp.route("/GoTo")
def goto_page():
    """外链安全确认页：非 yjlt.top 域名的链接先经此页确认再跳转。"""
    target = (request.args.get("to") or "").strip()
    if len(target) > 2048:
        target = ""
    return render_template("goto.html", goto_target=target)


@pages_bp.route("/favicon.ico")
def favicon():
    return redirect(url_for("static", filename="img/favicon.png"))
