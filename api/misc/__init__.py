"""杂项 API：会馆 / 彩蛋 / RSS（挂载根路径）。

接口：
    GET /api/huiguan   会馆列表（读 huiguan.json）
    GET /Easter-Egg    随机一条彩蛋（读 EasterEgg/1.json）
    GET /rss.xml       最新帖子 RSS（20 条）
"""
from __future__ import annotations

import json
import random
from pathlib import Path
from xml.sax.saxutils import escape as xml_escape

from flask import Blueprint, jsonify, Response

import db

misc_bp = Blueprint("misc", __name__)

_ROOT = Path(__file__).resolve().parent.parent.parent


def _load_json(name):
    try:
        with open(_ROOT / name, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


@misc_bp.route("/api/huiguan", methods=["GET"])
def api_huiguan():
    data = _load_json("huiguan.json")
    if data is None:
        return jsonify({"success": False, "message": "会馆数据加载失败"}), 500
    return jsonify({"success": True, "list": data})


@misc_bp.route("/Easter-Egg", methods=["GET"])
def api_easter_egg():
    data = _load_json("EasterEgg/1.json")
    if not data:
        return jsonify({"success": False, "message": "彩蛋数据加载失败"}), 500
    return jsonify(random.choice(data))


@misc_bp.route("/rss.xml", methods=["GET"])
def api_rss():
    """生成最新 20 条帖子 RSS 2.0。"""
    posts = db.post.get_post_list(1, 20)
    items = []
    for p in posts:
        link = f"{request_url_root()}/post/{p['id']}"
        items.append(
            "<item>"
            f"<title>{xml_escape(p['title'] or '')}</title>"
            f"<link>{xml_escape(link)}</link>"
            f"<description>{xml_escape(p['summary'] or '')}</description>"
            f"<pubDate>{xml_escape(p['created_at'] or '')}</pubDate>"
            "</item>"
        )
    xml = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<rss version="2.0"><channel>'
        "<title>妖精论坛</title><description>妖精论坛最新帖子</description>"
        f"<link>{xml_escape(request_url_root())}</link>"
        + "".join(items)
        + "</channel></rss>"
    )
    return Response(xml, mimetype="application/rss+xml; charset=utf-8")


def request_url_root():
    from flask import request
    return request.host_url.rstrip("/")
