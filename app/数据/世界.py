# 世界频道数据访问
"""世界频道相关数据库操作：发送消息、获取消息列表。"""

from app.数据 import get_conn, execute_query, execute_insert, safe_html


def SendWorldMessage(sender_id, sender_name, content, parent_id=None):
	"""发送世界频道消息，限制每用户每2秒只能发一条。支持引用回复。"""
	last = execute_query(
		"""
		SELECT created_at FROM World
		WHERE sender_id = %s
		ORDER BY created_at DESC
		LIMIT 1
		""",
		(sender_id,),
		fetch=True
	)
	if last and last[0]:
		from datetime import datetime
		now = datetime.now(last[0].tzinfo) if last[0].tzinfo else datetime.now()
		if (now - last[0]).total_seconds() < 2:
			return {"success": False, "message": "发言太快，请稍后再试"}
	execute_query("""
		DELETE FROM World
		WHERE created_at < NOW() - INTERVAL '5 minutes';
	""")
	execute_insert(
		"""
		INSERT INTO World (sender_id, sender_name, content, parent_id)
		VALUES (%s, %s, %s, %s)
		""",
		(sender_id, sender_name, safe_html(content), parent_id)
	)
	return {"success": True, "message": "发送成功"}


def GitWroldMessageWithAll():
	results = execute_query(
		"""
		SELECT id, sender_id, sender_name, content, parent_id, created_at
		FROM World
		ORDER BY created_at DESC
		LIMIT 100
		""",
		fetch_all=True
	)
	messages = []
	for message in results:
		messages.append({
			"id": message[0],
			"sender_id": message[1],
			"sender_name": message[2],
			"content": message[3],
			"parent_id": message[4],
			"created_at": message[5].isoformat() if message[5] else None
		})
	return messages
