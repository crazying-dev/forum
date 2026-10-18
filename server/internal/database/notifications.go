package database

import (
	"context"
	"crypto/sha256"
	"encoding/base64"
	"encoding/json"
	"errors"
	"fmt"
	"strings"
	"time"

	"github.com/jackc/pgx/v5"
)

// 通知类型（消息中心分类映射见 UnreadCounts）。
const (
	NotificationPostLike     = "post_like"
	NotificationCommentLike  = "comment_like"
	NotificationPostComment  = "post_comment"
	NotificationCommentReply = "comment_reply"
	NotificationSystem       = "system"
)

// NotificationInput 创建一条站内通知。
// DedupeKey 非空时由 uq_notifications_dedupe 保证幂等（同一 key 只落一行）。
type NotificationInput struct {
	UserID           string
	Type             string
	ActorID          string
	TargetType       string
	TargetID         string
	ContextPostID    string
	ContextCommentID string
	Payload          map[string]any
	DedupeKey        string
}

// normalizeDedupeKey 将去重键限制在列宽 160 内；超长时使用 sha256 摘要，避免截断碰撞。
func normalizeDedupeKey(key string) string {
	key = strings.TrimSpace(key)
	if len(key) <= 160 {
		return key
	}
	sum := sha256.Sum256([]byte(key))
	return fmt.Sprintf("h:%x", sum[:])
}

// CreateNotificationTx 在事务内创建通知；dedupe_key 冲突时返回 created=false（幂等）。
func (d *DB) CreateNotificationTx(ctx context.Context, tx pgx.Tx, in NotificationInput) (id int64, created bool, err error) {
	if in.UserID == "" || in.Type == "" {
		return 0, false, fmt.Errorf("notification: user_id/type 不能为空")
	}
	payload := []byte("{}")
	if len(in.Payload) > 0 {
		payload, err = json.Marshal(in.Payload)
		if err != nil {
			return 0, false, fmt.Errorf("notification: payload: %w", err)
		}
	}
	err = tx.QueryRow(ctx, `INSERT INTO notifications
		(user_id, type, actor_id, target_type, target_id, context_post_id, context_comment_id, payload, dedupe_key)
		VALUES ($1, $2, $3, $4, $5, $6, $7, $8::jsonb, $9)
		ON CONFLICT (dedupe_key) WHERE dedupe_key <> '' DO NOTHING
		RETURNING id`,
		in.UserID, in.Type, in.ActorID, in.TargetType, in.TargetID, in.ContextPostID, in.ContextCommentID,
		payload, normalizeDedupeKey(in.DedupeKey)).Scan(&id)
	if errors.Is(err, pgx.ErrNoRows) {
		return 0, false, nil
	}
	if err != nil {
		return 0, false, err
	}
	return id, true, nil
}

// CreateNotification 非事务便捷入口。
func (d *DB) CreateNotification(ctx context.Context, in NotificationInput) (int64, bool, error) {
	var id int64
	var created bool
	err := d.Tx(ctx, func(tx pgx.Tx) error {
		var e error
		id, created, e = d.CreateNotificationTx(ctx, tx, in)
		return e
	})
	return id, created, err
}

// UnreadCounts 消息中心四类未读数。只统计各类 last_read_at 之后产生的消息。
type UnreadCounts struct {
	Likes    int `json:"likes"`
	Comments int `json:"comments"`
	System   int `json:"system"`
	Chat     int `json:"chat"`
}

// UnreadCounts 统计 likes/comments/system（message_read_state）与 chat（chat_members）未读。
func (d *DB) UnreadCounts(ctx context.Context, userID string) (UnreadCounts, error) {
	var counts UnreadCounts
	const epoch = "'epoch'::timestamptz"
	err := d.QueryRow(ctx, `SELECT
		(SELECT COUNT(*) FROM notifications n
			WHERE n.user_id = $1 AND n.type IN ('post_like', 'comment_like')
			AND n.created_at > COALESCE((SELECT last_read_at FROM message_read_state WHERE user_id = $1 AND category = 'likes'), `+epoch+`)),
		(SELECT COUNT(*) FROM notifications n
			WHERE n.user_id = $1 AND n.type IN ('post_comment', 'comment_reply')
			AND n.created_at > COALESCE((SELECT last_read_at FROM message_read_state WHERE user_id = $1 AND category = 'comments'), `+epoch+`)),
		(SELECT COUNT(*) FROM broadcast_notices b
			WHERE b.published_at <= NOW() AND b.published_at > COALESCE((SELECT last_read_at FROM message_read_state WHERE user_id = $1 AND category = 'system'), `+epoch+`))
		+
		(SELECT COUNT(*) FROM notifications n
			WHERE n.user_id = $1 AND n.type = 'system'
			AND n.created_at > COALESCE((SELECT last_read_at FROM message_read_state WHERE user_id = $1 AND category = 'system'), `+epoch+`))`,
		userID).Scan(&counts.Likes, &counts.Comments, &counts.System)
	if err != nil {
		return counts, err
	}
	chat, err := d.ChatUnread(ctx, userID)
	if err != nil {
		return counts, err
	}
	counts.Chat = chat
	return counts, nil
}

// validMessageCategory 可标记已读的消息分类（chat 走 chat_members，不在此表）。
func validMessageCategory(category string) bool {
	switch category {
	case "likes", "comments", "system":
		return true
	}
	return false
}

// MarkRead 更新某类消息的已读时间（只前进不后退）。
func (d *DB) MarkRead(ctx context.Context, userID, category string, lastReadAt time.Time) error {
	if !validMessageCategory(category) {
		return fmt.Errorf("message: 非法分类 %q", category)
	}
	if lastReadAt.IsZero() {
		lastReadAt = time.Now().UTC()
	}
	_, err := d.Exec(ctx, `INSERT INTO message_read_state (user_id, category, last_read_at)
		VALUES ($1, $2, $3)
		ON CONFLICT (user_id, category) DO UPDATE
		SET last_read_at = GREATEST(message_read_state.last_read_at, EXCLUDED.last_read_at)`,
		userID, category, lastReadAt)
	return err
}

// SystemMessage 消息中心「系统」条目（广播通知或 per-user system 通知）。
type SystemMessage struct {
	ID        int64     `json:"id"`
	Type      string    `json:"type"`
	Title     string    `json:"title"`
	BodyHTML  string    `json:"body_html"`
	Link      string    `json:"link"`
	CreatedAt time.Time `json:"created_at"`
	Source    string    `json:"-"` // broadcast / user（不对外）
}

// BroadcastNotice 全局广播通知。
type BroadcastNotice struct {
	ID          int64     `json:"id"`
	Type        string    `json:"type"`
	Title       string    `json:"title"`
	BodyHTML    string    `json:"body_html"`
	Link        string    `json:"link"`
	PublishedAt time.Time `json:"published_at"`
}

// BroadcastList 全局广播通知（id 倒序 cursor 分页）。
func (d *DB) BroadcastList(ctx context.Context, cursor string, limit int) ([]BroadcastNotice, bool, error) {
	limit = normalizeLimit(limit, 20, 50)
	cursorID := parseNumericCursor(cursor)
	rows, err := d.Query(ctx, `SELECT id, type, title, body_html, link, published_at
		FROM broadcast_notices
		WHERE ($1 = 0 OR id < $1) AND published_at <= NOW()
		ORDER BY id DESC LIMIT $2`, cursorID, limit+1)
	if err != nil {
		return nil, false, err
	}
	defer rows.Close()
	items := []BroadcastNotice{}
	for rows.Next() {
		var n BroadcastNotice
		if err := rows.Scan(&n.ID, &n.Type, &n.Title, &n.BodyHTML, &n.Link, &n.PublishedAt); err != nil {
			return nil, false, err
		}
		items = append(items, n)
	}
	if err := rows.Err(); err != nil {
		return nil, false, err
	}
	hasMore := len(items) > limit
	if hasMore {
		items = items[:limit]
	}
	return items, hasMore, nil
}

// SystemCursor 编码系统消息分页游标（created_at + 来源 + id，避免广播/用户通知同秒同 id 的边界问题）。
func SystemCursor(createdAt time.Time, source string, id int64) string {
	return base64.RawURLEncoding.EncodeToString([]byte(fmt.Sprintf("%d|%s|%d", createdAt.UnixNano(), source, id)))
}

func decodeSystemCursor(cursor string) (time.Time, string, int64, bool) {
	raw, err := base64.RawURLEncoding.DecodeString(strings.TrimSpace(cursor))
	if err != nil {
		return time.Time{}, "", 0, false
	}
	parts := strings.Split(string(raw), "|")
	if len(parts) != 3 {
		return time.Time{}, "", 0, false
	}
	var nanos int64
	var id int64
	if _, err := fmt.Sscanf(parts[0], "%d", &nanos); err != nil {
		return time.Time{}, "", 0, false
	}
	if _, err := fmt.Sscanf(parts[2], "%d", &id); err != nil {
		return time.Time{}, "", 0, false
	}
	return time.Unix(0, nanos).UTC(), parts[1], id, true
}

// ListSystem 合并「全局广播」与「per-user system 通知」，按时间倒序 cursor 分页。
// 返回的 nextCursor 在 hasMore=false 时为空。
func (d *DB) ListSystem(ctx context.Context, userID, cursor string, limit int) ([]SystemMessage, bool, string, error) {
	limit = normalizeLimit(limit, 20, 50)
	var (
		cursorTime   = time.Time{}
		cursorSource = ""
		cursorID     int64
	)
	if strings.TrimSpace(cursor) != "" {
		t, source, id, ok := decodeSystemCursor(cursor)
		if !ok {
			return nil, false, "", fmt.Errorf("message: 非法系统消息游标")
		}
		cursorTime, cursorSource, cursorID = t, source, id
	}
	rows, err := d.Query(ctx, `
		WITH merged AS (
			SELECT b.id, 'broadcast'::text AS source, b.type, b.title, b.body_html, b.link, b.published_at AS created_at
			FROM broadcast_notices b
			WHERE b.published_at <= NOW()
			UNION ALL
			SELECT n.id, 'user'::text AS source, n.type,
				COALESCE(n.payload->>'title', ''), COALESCE(n.payload->>'body_html', ''), COALESCE(n.payload->>'link', ''),
				n.created_at
			FROM notifications n
			WHERE n.user_id = $1 AND n.type = 'system'
		)
		SELECT id, source, type, title, body_html, link, created_at
		FROM merged
		WHERE $2 = '' OR (created_at, source, id) < ($3, $4, $5)
		ORDER BY created_at DESC, source DESC, id DESC
		LIMIT $6`, userID, strings.TrimSpace(cursor), cursorTime, cursorSource, cursorID, limit+1)
	if err != nil {
		return nil, false, "", err
	}
	defer rows.Close()
	items := []SystemMessage{}
	for rows.Next() {
		var m SystemMessage
		if err := rows.Scan(&m.ID, &m.Source, &m.Type, &m.Title, &m.BodyHTML, &m.Link, &m.CreatedAt); err != nil {
			return nil, false, "", err
		}
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
		next = SystemCursor(last.CreatedAt, last.Source, last.ID)
	}
	return items, hasMore, next, nil
}
