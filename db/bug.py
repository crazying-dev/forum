"""Bug 反馈数据访问。"""
from db import execute_query


def report_bug(title, detail, steps="", contact="", reporter_id=None,
               reporter_name="", user_agent="", page_url=""):
    """提交 Bug 举报，返回 {"success": True, "id": report_id}。"""
    title = (title or "").strip()
    detail = (detail or "").strip()
    if not title or not detail:
        return {"success": False, "message": "标题与详细描述不能为空"}
    if len(title) > 200:
        title = title[:200]
    try:
        row = execute_query(
            """
            INSERT INTO bug_reports (title, detail, steps, contact, reporter_id,
                                     reporter_name, user_agent, page_url)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
            """,
            (title, detail, (steps or "").strip(), (contact or "").strip()[:200],
             reporter_id, (reporter_name or "")[:64], (user_agent or "")[:500],
             (page_url or "")[:500]),
            fetch=True,
        )
        return {"success": True, "id": row.get("id") if row else None}
    except Exception as e:
        return {"success": False, "message": f"提交失败: {e}"}
