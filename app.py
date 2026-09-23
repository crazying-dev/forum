"""Flask 应用工厂：创建、配置并返回 Flask app。"""
from __future__ import annotations

import os
import threading
import time

from flask import Flask, g, jsonify, request, send_from_directory

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
    # 静态资源浏览器强缓存 7 天（LPK/JS/CSS/图片等；ETag+Last-Modified 过期后 304 校验）
    app.config["SEND_FILE_MAX_AGE_DEFAULT"] = 604800

    # ── 代理信任（X-Forwarded-For / X-Forwarded-Proto） ──
    # 线上部署在 Nginx/Caddy 反向代理后：不开启时后端看到的连接方总是代理（127.0.0.1），
    # request.remote_addr、Werkzeug 访问日志、限流用的客户端 IP 全部拿不到真实来访 IP。
    # 开启后 REMOTE_ADDR 由 X-Forwarded-For 还原（x_for=1：只信任最近一跳代理，
    # 因此客户端伪造的 X-Forwarded-For 前缀不会被采信）。
    # 注意：仅当服务确实位于可信代理之后才可开启；可用环境变量 TRUST_PROXY=0 关闭。
    if os.getenv("TRUST_PROXY", "1") != "0":
        from werkzeug.middleware.proxy_fix import ProxyFix
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1)

    # ── 访问日志：显式打印真实客户端 IP ──
    # 形如：[access] ip=1.2.3.4 peer=127.0.0.1 GET /api/posts?page=1 200 12ms
    #   ip    = 真实来访 IP（经 ProxyFix 从 X-Forwarded-For 还原）
    #   peer  = 直连方（Nginx 代理时为 127.0.0.1，便于确认请求确实经代理转发）
    # 可用环境变量 ACCESS_LOG=0 关闭。
    _access_log = os.getenv("ACCESS_LOG", "1") != "0"

    @app.before_request
    def _access_log_mark():
        g._req_start = time.time()

    @app.after_request
    def _access_log_write(resp):
        if not _access_log:
            return resp
        try:
            real_ip = request.remote_addr or "-"
            # ProxyFix 会把原始 REMOTE_ADDR 存在 environ["werkzeug.proxy_fix.orig"]
            orig = request.environ.get("werkzeug.proxy_fix.orig") or {}
            peer = orig.get("REMOTE_ADDR") if isinstance(orig, dict) else None
            peer = peer or "-"
            cost_ms = int((time.time() - getattr(g, "_req_start", time.time())) * 1000)
            full = request.full_path
            target = full[:-1] if full.endswith("?") else full
            print(f"[access] ip={real_ip} peer={peer} {request.method} {target} {resp.status_code} {cost_ms}ms", flush=True)
        except Exception:
            pass
        return resp

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

    # ── 模板全局变量：静态资源缓存版本号（更新资源后改 config.STATIC_VERSION） ──
    @app.context_processor
    def _inject_static_version():
        return {"static_version": getattr(config, "STATIC_VERSION", "1")}

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
    # max_age=0：头像会被用户更新，不做强缓存（仍带 ETag/304 校验）
    @app.route("/avatar/<path:filename>")
    def serve_avatar(filename):
        return send_from_directory(config.AVATAR_UPLOAD_DIR, filename, max_age=0)

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
