package database

import (
	"context"
	"strconv"
	"time"

	"github.com/jackc/pgx/v5"
)

// ChatMessage 管理团队聊天消息。
type ChatMessage struct {
	ID            int64     `json:"id"`
	SenderType    string    `json:"sender_type"` // user / admin
	SenderName    string    `json:"sender_name"`
	SenderAvatar  string    `json:"sender_avatar"`
	AdminID       string    `json:"admin_id"`
	ContentHTML   string    `json:"content_html"`
	ContentFormat string    `json:"content_format"`
	CreatedAt     time.Time `json:"created_at"`
}

// EnsureChatRoom 获取/创建用户的管理团队聊天室，并确保 user 成员行存在。
func (d *DB) EnsureChatRoom(ctx context.Context, userID string) (int64, error) {
	var roomID int64
	err := d.Tx(ctx, func(tx pgx.Tx) error {
		var e error
		roomID, e = ensureChatRoomTx(ctx, tx, userID)
		return e
	})
	return roomID, err
}

func ensureChatRoomTx(ctx context.Context, tx pgx.Tx, userID string) (int64, error) {
	var roomID int64
	// 无实际变更的 UPDATE 用于在并发下安全 RETURNING id。
	err := tx.QueryRow(ctx, `INSERT INTO chat_rooms (user_id) VALUES ($1)
		ON CONFLICT (user_id) DO UPDATE SET user_id = EXCLUDED.user_id
		RETURNING id`, userID).Scan(&roomID)
	if err != nil {
		return 0, err
	}
	if _, err := tx.Exec(ctx, `INSERT INTO chat_members (room_id, member_type, member_id)
		VALUES ($1, 'user', $2) ON CONFLICT DO NOTHING`, roomID, userID); err != nil {
		return 0, err
	}
	return roomID, nil
}

// GetChatMessages 聊天消息列表（id 倒序 cursor 分页）。
func (d *DB) GetChatMessages(ctx context.Context, userID, cursor string, limit int) ([]ChatMessage, bool, error) {
	limit = normalizeLimit(limit, 20, 50)
	cursorID := parseNumericCursor(cursor)
	roomID, err := d.EnsureChatRoom(ctx, userID)
	if err != nil {
		return nil, false, err
	}
	rows, err := d.Query(ctx, `SELECT m.id, m.sender_type,
			COALESCE(NULLIF(m.forum_account_name, ''), u.name, m.admin_id),
			COALESCE(NULLIF(m.forum_account_avatar, ''), u.avatar, ''),
			m.admin_id, m.content_html, m.content_format, m.created_at
		FROM chat_messages m
		LEFT JOIN users u ON u.id = m.forum_account_id
		WHERE m.room_id = $1 AND ($2 = 0 OR m.id < $2)
		ORDER BY m.id DESC LIMIT $3`, roomID, cursorID, limit+1)
	if err != nil {
		return nil, false, err
	}
	defer rows.Close()
	items := []ChatMessage{}
	for rows.Next() {
		var m ChatMessage
		if err := rows.Scan(&m.ID, &m.SenderType, &m.SenderName, &m.SenderAvatar, &m.AdminID,
			&m.ContentHTML, &m.ContentFormat, &m.CreatedAt); err != nil {
			return nil, false, err
		}
		items = append(items, m)
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

// CreateChatMessage 用户发送一条聊天消息（快照发送者名称/头像，供后台展示）。
func (d *DB) CreateChatMessage(ctx context.Context, userID, contentHTML string) (*ChatMessage, error) {
	var msg ChatMessage
	err := d.Tx(ctx, func(tx pgx.Tx) error {
		roomID, err := ensureChatRoomTx(ctx, tx, userID)
		if err != nil {
			return err
		}
		var name, avatar string
		if err := tx.QueryRow(ctx, `SELECT COALESCE(name, ''), COALESCE(avatar, '') FROM users WHERE id = $1`, userID).Scan(&name, &avatar); err != nil {
			return err
		}
		var createdAt time.Time
		if err := tx.QueryRow(ctx, `INSERT INTO chat_messages
			(room_id, sender_type, forum_account_id, forum_account_name, forum_account_avatar, content_html, content_format)
			VALUES ($1, 'user', $2, $3, $4, $5, 'html')
			RETURNING id, created_at`, roomID, userID, name, avatar, contentHTML).Scan(&msg.ID, &createdAt); err != nil {
			return err
		}
		msg.SenderType = "user"
		msg.SenderName = name
		msg.SenderAvatar = avatar
		msg.ContentHTML = contentHTML
		msg.ContentFormat = "html"
		msg.CreatedAt = createdAt
		return syncMediaReferencesTx(ctx, tx, "chat_message", strconv.FormatInt(msg.ID, 10), contentHTML)
	})
	if err != nil {
		return nil, err
	}
	return &msg, nil
}

// GetChatMessagesAfter 拉取用户聊天室中 id > afterID 的新消息（升序，供 SSE 轮询兜底）。
func (d *DB) GetChatMessagesAfter(ctx context.Context, userID string, afterID int64, limit int) ([]ChatMessage, error) {
	if limit <= 0 || limit > 50 {
		limit = 20
	}
	rows, err := d.Query(ctx, `SELECT m.id, m.sender_type,
			COALESCE(NULLIF(m.forum_account_name, ''), u.name, m.admin_id),
			COALESCE(NULLIF(m.forum_account_avatar, ''), u.avatar, ''),
			m.admin_id, m.content_html, m.content_format, m.created_at
		FROM chat_messages m
		JOIN chat_rooms r ON r.id = m.room_id
		LEFT JOIN users u ON u.id = m.forum_account_id
		WHERE r.user_id = $1 AND m.id > $2
		ORDER BY m.id ASC LIMIT $3`, userID, afterID, limit)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	items := []ChatMessage{}
	for rows.Next() {
		var m ChatMessage
		if err := rows.Scan(&m.ID, &m.SenderType, &m.SenderName, &m.SenderAvatar, &m.AdminID,
			&m.ContentHTML, &m.ContentFormat, &m.CreatedAt); err != nil {
			return nil, err
		}
		items = append(items, m)
	}
	return items, rows.Err()
}

// LatestChatMessageID 用户聊天室当前最大消息 ID（SSE 建连时作为轮询起点）。
func (d *DB) LatestChatMessageID(ctx context.Context, userID string) (int64, error) {
	var id int64
	err := d.QueryRow(ctx, `SELECT COALESCE(MAX(m.id), 0) FROM chat_messages m JOIN chat_rooms r ON r.id = m.room_id WHERE r.user_id = $1`, userID).Scan(&id)
	return id, err
}

// MarkChatRead 更新用户聊天室已读游标（只前进不后退）。
func (d *DB) MarkChatRead(ctx context.Context, userID string, lastMessageID int64) error {
	if lastMessageID < 0 {
		lastMessageID = 0
	}
	roomID, err := d.EnsureChatRoom(ctx, userID)
	if err != nil {
		return err
	}
	_, err = d.Exec(ctx, `UPDATE chat_members
		SET last_read_message_id = GREATEST(last_read_message_id, $3), updated_at = NOW()
		WHERE room_id = $1 AND member_type = 'user' AND member_id = $2`, roomID, userID, lastMessageID)
	return err
}

// ChatUnread 用户聊天室未读数（不统计自己发出的消息）。
func (d *DB) ChatUnread(ctx context.Context, userID string) (int, error) {
	var count int
	err := d.QueryRow(ctx, `SELECT COUNT(*)
		FROM chat_rooms r
		LEFT JOIN chat_members cm ON cm.room_id = r.id AND cm.member_type = 'user' AND cm.member_id = $1
		JOIN chat_messages m ON m.room_id = r.id
		WHERE r.user_id = $1
			AND m.id > COALESCE(cm.last_read_message_id, 0)
			AND NOT (m.sender_type = 'user' AND m.forum_account_id = $1)`, userID).Scan(&count)
	return count, err
}
