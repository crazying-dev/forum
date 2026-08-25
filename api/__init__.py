"""API 模块化入口。

所有子 Blueprint 在这里统一注册，然后由 app.py 挂载。
"""
from __future__ import annotations

from flask import Flask

from .pages import pages_bp
from .user import user_bp
from .post import post_bp
from .comment import comment_bp
from .world import world_bp
from .search import search_bp
from .bug import bug_bp
from .email import email_bp
from .misc import misc_bp


def register_blueprints(app: Flask) -> None:
    """把各子模块 Blueprint 注册到 app。"""
    app.register_blueprint(user_bp, url_prefix="/api/user")
    app.register_blueprint(post_bp, url_prefix="/api/posts")
    app.register_blueprint(comment_bp, url_prefix="/api")
    app.register_blueprint(world_bp, url_prefix="/api/world")
    app.register_blueprint(search_bp, url_prefix="/api")
    app.register_blueprint(bug_bp, url_prefix="/api")
    app.register_blueprint(email_bp, url_prefix="/api")
    app.register_blueprint(misc_bp)
    app.register_blueprint(pages_bp)


__all__ = [
    "register_blueprints",
    "user_bp",
    "post_bp",
    "comment_bp",
    "world_bp",
    "search_bp",
    "bug_bp",
    "email_bp",
    "misc_bp",
]
