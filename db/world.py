"""世界频道数据访问。"""
from db import execute_query, execute_insert, safe_html


def get_world_messages(limit=100):
    """获取世界频道最近消息（按时间倒序）。"""
    rows = execute_query(
        "SELECT w.id, w.sender_id, w.sender_name, w.content, w.parent_id, w.created_at, "
        "u.avatar AS sender_avatar FROM world w "
        "LEFT JOIN users u ON w.sender_id = u.id "
        "ORDER BY w.created_at DESC LIMIT %s",
        (limit,),
        fetch_all=True,
    )
    messages = []
    for r in rows:
        messages.append({
            "id": r.get("id"),
            "sender_id": r.get("sender_id"),
            "sender_name": r.get("sender_name"),
            "content": r.get("content"),
            "parent_id": r.get("parent_id"),
            "sender_avatar": r.get("sender_avatar"),
            "created_at": str(r.get("created_at")) if r.get("created_at") else None,
        })
    return messages


def send_world_message(sender_id, sender_name, content, parent_id=None):
    """发送世界频道消息；每用户 2 秒限一条；保留最近 1000 条。"""
    last = execute_query(
        "SELECT created_at FROM world WHERE sender_id = %s ORDER BY created_at DESC LIMIT 1",
        (sender_id,),
        fetch=True,
    )
    if last and last.get("created_at"):
        from datetime import datetime
        ts = last["created_at"]
        now = datetime.now(ts.tzinfo) if ts.tzinfo else datetime.now()
        if (now - ts).total_seconds() < 2:
            return {"success": False, "message": "发言太快，请稍后再试"}
    # WebSocket 常驻场景：仅保留最近 1000 条（不再清理 5 分钟历史）
    execute_query(
        "DELETE FROM world WHERE id NOT IN (SELECT id FROM world ORDER BY id DESC LIMIT 1000)"
    )
    row = execute_query(
        "INSERT INTO world (sender_id, sender_name, content, parent_id) "
        "VALUES (%s, %s, %s, %s) "
        "RETURNING id, sender_id, sender_name, content, parent_id, created_at",
        (sender_id, sender_name, safe_html(content), parent_id),
        fetch=True,
    )
    if not row:
        return {"success": False, "message": "发送失败"}
    msg = {
        "id": row.get("id"),
        "sender_id": row.get("sender_id"),
        "sender_name": row.get("sender_name"),
        "content": row.get("content"),
        "parent_id": row.get("parent_id"),
        "created_at": str(row.get("created_at")) if row.get("created_at") else None,
    }
    return {"success": True, "message": "发送成功", "msg": msg}
