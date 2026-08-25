"""Flask 应用工厂：创建、配置并返回 Flask app。"""
from __future__ import annotations

import os
import threading

from flask import Flask, jsonify, request, send_from_directory

import config
import db
import api
from api.user import _authenticate_from_cookies


def create_app() -> Flask:
    """构建 Flask 应用实例。"""
    app = Flask(__name__)
    _db_init_lock = threading.Lock()
    _db_inited = {"done": False}

    # ── 基础配置 ──
    app.config["JSON_AS_ASCII"] = False
    app.config["JSON_SORT_KEYS"] = False
    app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "TestKeyFor1")
    app.config["MAX_CONTENT_LENGTH"] = 20 * 1024 * 1024  # 20MB 请求上限

    # ── 代理信任（X-Forwarded-For / X-Forwarded-Proto） ──
    # 线上环境部署在 Nginx/Caddy 后，需开启；注释掉表示不信任代理头。
    # from werkzeug.middleware.proxy_fix import ProxyFix
    # app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1)

    # ── CORS（简化实现，生产建议装 flask-cors 包） ──
    @app.after_request
    def _add_cors(resp):
        origin = request.headers.get("Origin")
        if origin:
            resp.headers["Access-Control-Allow-Origin"] = origin
            resp.headers["Access-Control-Allow-Credentials"] = "true"
            resp.headers["Access-Control-Allow-Headers"] = (
                "Content-Type, Authorization, X-Requested-With"
            )
            resp.headers["Access-Control-Allow-Methods"] = (
                "GET, POST, PUT, DELETE, OPTIONS, PATCH"
            )
        return resp

    # ── 数据库初始化（首次请求兜底执行一次，替代被废弃的 before_first_request） ──
    def _ensure_db_once():
        if _db_inited["done"]:
            return
        with _db_init_lock:
            if _db_inited["done"]:
                return
            try:
                db.init_database()
            except Exception as e:
                print(f"[DB] 首次请求建表失败: {e}")
            finally:
                _db_inited["done"] = True

    # ── 全局统一鉴权：从 cookie 读 token+ID，验证后挂到 g.user ──
    @app.before_request
    def _auth_middleware():
        # CORS 预检直接放行
        if request.method == "OPTIONS":
            return ("", 204)
        _ensure_db_once()
        _authenticate_from_cookies()

    # ── 健康检查 ──
    @app.route("/healthz", methods=["GET"])
    def healthz():
        return jsonify({"ok": True, "service": "forum-new"}), 200

    # ── 头像静态资源：/avatar/<file> → AVATAR_UPLOAD_DIR/<file> ──
    @app.route("/avatar/<path:filename>")
    def serve_avatar(filename):
        return send_from_directory(config.AVATAR_UPLOAD_DIR, filename)

    # ── 根路径：由 pages_bp 渲染首页（JSON index 已移除）──

    # ── 统一注册各 API 模块 Blueprint ──
    api.register_blueprints(app)

    # ── 兜底错误处理 ──
    @app.errorhandler(404)
    def _not_found(_):
        return jsonify({"success": False, "message": "接口不存在"}), 404

    @app.errorhandler(405)
    def _method_not_allowed(_):
        return jsonify({"success": False, "message": "请求方法不允许"}), 405

    @app.errorhandler(500)
    def _server_error(e):
        app.logger.exception(e)
        return jsonify({"success": False, "message": "服务器内部错误"}), 500

    return app
