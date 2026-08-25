"""页面路由：渲染前端模板。"""
from flask import Blueprint, render_template, redirect, request, url_for

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
    mode_arg = request.args.get("mode") or "reset"
    token = request.args.get("token") or ""
    target = url_for("pages.auth", mode=mode_arg)
    if token:
        target += ("&" if "?" in target else "?") + "token=" + token
    return redirect(target)


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


@pages_bp.route("/WIKI/Personal/Live2D")
def wiki_personal_live2d():
    return redirect("/Live2D")


@pages_bp.route("/Live2D")
def live2d():
    return render_template("live2d.html", show_world=False, show_global_live2d=False)


@pages_bp.route("/favicon.ico")
def favicon():
    return redirect("https://img.crazying-dev.top/text/one/favicon.png")
