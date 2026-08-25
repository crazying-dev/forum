"""服务启动入口。

运行:
    python main.py       # 调试模式: 0.0.0.0:3000
    gunicorn main:app    # 生产模式（Linux）
    waitress-serve main:app  # 生产模式（Windows/Linux 通用）
"""
from __future__ import annotations

import os
import sys

# 防御性路径注入：uv 的 package=false 模式下，.venv 的 site-packages 会抢先于 CWD，
# 导致 waitress-serve 或子进程里找不到本项目的 api/ db/ tool 等源码包。
# 基于 __file__ 定位项目根目录（而不是 CWD），插入到 sys.path[0] 保证最高优先级。
_PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from app import create_app

app = create_app()


if __name__ == "__main__":
    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", "3000"))
    debug = os.getenv("FLASK_DEBUG", "0") == "1"

    # TODO: 接入安全模块，上线前补上恶意 IP 拦截
    # from security import blacklist_middleware
    # app.before_request(blacklist_middleware)

    # 启动时尝试建表（忽略失败，无 DB 配置下也能跑健康检查）
    try:
        import db
        db.init_database()
    except Exception as e:
        print(f"[DB] 启动时建表失败（若未配置 DATABASE_URL 可忽略）: {e}")

    print(f"[forum-new] Listening on {host}:{port}, debug={debug}")
    app.run(host=host, port=port, debug=debug)
