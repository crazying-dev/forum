package database

import (
	"context"
	"encoding/base64"
	"fmt"
	"strconv"
	"strings"
	"time"
)

// MessageActor 消息中心里的触发者摘要。
type MessageActor struct {
	ID     string `json:"id"`
	Name   string `json:"name"`
	Avatar string `json:"avatar"`
}

// LikeMessage 点赞消息（帖子赞 + 评论赞，全部历史）。
// ID 为 "pl_<post_likes.id>" / "cl_<comment_likes.id>" 形式的稳定标识（同时用于游标）。
type LikeMessage struct {
	ID             string       `json:"id"`
	Actor          MessageActor `json:"actor"`
	TargetType     string       `json:"target_type"`
	TargetID       string       `json:"target_id"`
	PostID         string       `json:"post_id"`
	PostTitle      string       `json:"post_title"`
	CommentID      string       `json:"comment_id"`
	CommentExcerpt string       `json:"comment_excerpt"`
	CreatedAt      time.Time    `json:"created_at"`
}

// CommentMessage 评论/回复消息（收到的评论：帖子下的新评论 + 对我的回复）。
type CommentMessage struct {
	ID        string       `json:"id"`
	Actor     MessageActor `json:"actor"`
	CommentID string       `json:"comment_id"`
	PostID    string       `json:"post_id"`
	PostTitle string       `json:"post_title"`
	Excerpt   string       `json:"excerpt"`
	ParentID  string       `json:"parent_id"`
	CreatedAt time.Time    `json:"created_at"`
}

// excerptExpr 历史评论可能是 html/markdown：html 先剥标签，再截断 120 字。
const excerptExpr = `CASE WHEN c.id IS NULL THEN ''
	WHEN c.content_format = 'html' THEN LEFT(regexp_replace(c.content, '<[^>]+>', '', 'g'), 120)
	ELSE LEFT(c.content, 120) END`

func normalizeLimit(limit, def, max int) int {
	if limit <= 0 {
		return def
	}
	if limit > max {
		return max
	}
	return limit
}

// parseNumericCursor 解析 id 型 cursor；非法/空值按 0（第一页）处理。
func parseNumericCursor(cursor string) int64 {
	v, err := strconv.ParseInt(strings.TrimSpace(cursor), 10, 64)
	if err != nil || v < 0 {
		return 0
	}
	return v
}

// CursorID 将 id 转为对外 cursor 字符串。
func CursorID(id int64) string { return strconv.FormatInt(id, 10) }

// encodeMessageCursor 消息游标：<created_at unixnano>|<source>|<row id>（Base64URL，不透明）。
func encodeMessageCursor(createdAt time.Time, source, rowID string) string {
	return base64.RawURLEncoding.EncodeToString([]byte(fmt.Sprintf("%d|%s|%s", createdAt.UnixNano(), source, rowID)))
}

func decodeMessageCursor(cursor string) (time.Time, string, string, bool) {
	raw, err := base64.RawURLEncoding.DecodeString(strings.TrimSpace(cursor))
	if err != nil {
		return time.Time{}, "", "", false
	}
	parts := strings.SplitN(string(raw), "|", 3)
	if len(parts) != 3 {
		return time.Time{}, "", "", false
	}
	var nanos int64
	if _, err := fmt.Sscanf(parts[0], "%d", &nanos); err != nil {
		return time.Time{}, "", "", false
	}
	return time.Unix(0, nanos).UTC(), parts[1], parts[2], true
}

// ListLikeMessages 点赞消息：post_likes ∪ comment_likes 全部历史，按时间倒序 cursor 分页。
// 返回 items, has_more, next_cursor, err。
func (d *DB) ListLikeMessages(ctx context.Context, userID, cursor string, limit int) ([]LikeMessage, bool, string, error) {
	limit = normalizeLimit(limit, 20, 50)
	var (
		cursorTime   time.Time
		cursorSource string
		cursorRowID  int64
	)
	if strings.TrimSpace(cursor) != "" {
		t, source, rowID, ok := decodeMessageCursor(cursor)
		if !ok {
			return nil, false, "", fmt.Errorf("message: 非法点赞游标")
		}
		if _, err := fmt.Sscanf(rowID, "%d", &cursorRowID); err != nil {
			return nil, false, "", fmt.Errorf("message: 非法点赞游标")
		}
		cursorTime, cursorSource = t, source
	}
	rows, err := d.Query(ctx, `
		WITH items AS (
			SELECT 'post_like'::text AS source, pl.id AS row_id, pl.user_id AS actor_id,
				pl.post_id AS post_id, ''::text AS comment_id, pl.created_at
			FROM post_likes pl
			JOIN posts p ON p.id = pl.post_id
			WHERE p.user_id = $1 AND p.status = 1 AND p.published_at <= NOW()
			UNION ALL
			SELECT 'comment_like'::text, cl.id, cl.user_id, c.post_id, cl.comment_id, cl.created_at
			FROM comment_likes cl
			JOIN comments c ON c.id = cl.comment_id
			JOIN posts p ON p.id = c.post_id
			WHERE c.user_id = $1 AND c.status = 1 AND p.status = 1 AND p.published_at <= NOW()
		)
		SELECT i.source, i.row_id, COALESCE(i.actor_id, ''), COALESCE(u.name, ''), COALESCE(u.avatar, ''),
			CASE WHEN i.source = 'post_like' THEN 'post' ELSE 'comment' END AS target_type,
			CASE WHEN i.source = 'post_like' THEN i.post_id ELSE i.comment_id END AS target_id,
			i.post_id, COALESCE(p.title, ''), i.comment_id,
			`+excerptExpr+`,
			i.created_at
		FROM items i
		LEFT JOIN users u ON u.id = i.actor_id
		LEFT JOIN posts p ON p.id = i.post_id
		LEFT JOIN comments c ON c.id = i.comment_id
		WHERE $2 = '' OR (i.created_at, i.source, i.row_id) < ($3, $4, $5)
		ORDER BY i.created_at DESC, i.source DESC, i.row_id DESC
		LIMIT $6`, userID, strings.TrimSpace(cursor), cursorTime, cursorSource, cursorRowID, limit+1)
	if err != nil {
		return nil, false, "", err
	}
	defer rows.Close()
	items := []LikeMessage{}
	for rows.Next() {
		var m LikeMessage
		var source string
		var rowID int64
		if err := rows.Scan(&source, &rowID, &m.Actor.ID, &m.Actor.Name, &m.Actor.Avatar,
			&m.TargetType, &m.TargetID, &m.PostID, &m.PostTitle, &m.CommentID, &m.CommentExcerpt, &m.CreatedAt); err != nil {
			return nil, false, "", err
		}
		prefix := "pl_"
		if source == "comment_like" {
			prefix = "cl_"
		}
		m.ID = prefix + strconv.FormatInt(rowID, 10)
		items = append(items, m)
	}
	if err := rows.Err(); err != nil {
		return nil, false, "", err
	}
	hasMore := len(items) > limit
	if hasMore {
		items = items[:limit]
	}
	next := ""
	if hasMore && len(items) > 0 {
		last := items[len(items)-1]
		source := "post_like"
		if strings.HasPrefix(last.ID, "cl_") {
			source = "comment_like"
		}
		rowID, _ := strconv.ParseInt(strings.TrimPrefix(strings.TrimPrefix(last.ID, "pl_"), "cl_"), 10, 64)
		next = encodeMessageCursor(last.CreatedAt, source, strconv.FormatInt(rowID, 10))
	}
	return items, hasMore, next, nil
}

// ListCommentMessages 评论消息：我的帖子下的评论 + 对我的评论的回复（全部历史），按时间倒序 cursor 分页。
func (d *DB) ListCommentMessages(ctx context.Context, userID, cursor string, limit int) ([]CommentMessage, bool, string, error) {
	limit = normalizeLimit(limit, 20, 50)
	var (
		cursorTime time.Time
		cursorID   string
	)
	if strings.TrimSpace(cursor) != "" {
		t, _, id, ok := decodeMessageCursor(cursor)
		if !ok {
			return nil, false, "", fmt.Errorf("message: 非法评论游标")
		}
		cursorTime, cursorID = t, id
	}
	rows, err := d.Query(ctx, `
		SELECT c.id, COALESCE(c.user_id, ''), COALESCE(u.name, ''), COALESCE(u.avatar, ''),
			c.post_id, COALESCE(p.title, ''),
			`+excerptExpr+`,
			COALESCE(c.parent_id::text, ''), c.created_at
		FROM comments c
		JOIN posts p ON p.id = c.post_id
		JOIN users u ON u.id = c.user_id
		WHERE c.status = 1 AND p.status = 1 AND p.published_at <= NOW() AND c.user_id <> $1
			AND (p.user_id = $1 OR EXISTS (
				SELECT 1 FROM comments pc WHERE pc.id = c.parent_id AND pc.user_id = $1 AND pc.status = 1
			))
			AND ($2 = '' OR (c.created_at, c.id) < ($3, $4))
		ORDER BY c.created_at DESC, c.id DESC
		LIMIT $5`, userID, strings.TrimSpace(cursor), cursorTime, cursorID, limit+1)
	if err != nil {
		return nil, false, "", err
	}
	defer rows.Close()
	items := []CommentMessage{}
	for rows.Next() {
		var m CommentMessage
		if err := rows.Scan(&m.ID, &m.Actor.ID, &m.Actor.Name, &m.Actor.Avatar,
			&m.PostID, &m.PostTitle, &m.Excerpt, &m.ParentID, &m.CreatedAt); err != nil {
			return nil, false, "", err
		}
		m.CommentID = m.ID
		items = append(items, m)
	}
	if err := rows.Err(); err != nil {
		return nil, false, "", err
	}
	hasMore := len(items) > limit
	if hasMore {
		items = items[:limit]
	}
	next := ""
	if hasMore && len(items) > 0 {
		last := items[len(items)-1]
		next = encodeMessageCursor(last.CreatedAt, "comment", last.ID)
	}
	return items, hasMore, next, nil
}

// MarkCategoryRead 标记 likes/comments/system 分类已读（chat 使用 MarkChatRead）。
func (d *DB) MarkCategoryRead(ctx context.Context, userID, category string, lastReadAt time.Time) error {
	if category == "chat" {
		return fmt.Errorf("message: chat 分类请使用 MarkChatRead")
	}
	return d.MarkRead(ctx, userID, category, lastReadAt)
}
