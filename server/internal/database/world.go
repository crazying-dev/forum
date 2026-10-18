package database

import (
	"context"
	"errors"
	"log"
	"strconv"
	"time"

	"github.com/jackc/pgx/v5"
)

// 世界频道常量。
const (
	// WorldDefaultLimit 列表默认条数（对齐 backend-contract §3）。
	WorldDefaultLimit = 50
	// WorldMaxLimit 单次查询硬上限。
	WorldMaxLimit = 500
	// WorldKeepCount 清理后保留的最新消息数。
	WorldKeepCount = 10000

	// worldCleanupBatchSize 分批删除大小（契约要求 500-2000）。
	worldCleanupBatchSize = 1000

	// worldSendInterval 每用户发言最小间隔。
	worldSendInterval = 2 * time.Second

	// worldCleanupLockKey 清理任务的 advisory lock 键。
	worldCleanupLockKey = "world_messages_cleanup"
)

var (
	// ErrWorldRateLimited 触发 2 秒/用户限流。
	ErrWorldRateLimited = errors.New("世界频道发言过于频繁")
	// ErrWorldUserNotFound 发送者不存在（会话失效或账号已注销）。
	ErrWorldUserNotFound = errors.New("世界频道用户不存在")
)

// WorldMessage 世界频道消息（对外 JSON 形状对齐 backend-contract §3）。
// 发送者昵称/头像/会馆信息为写入时快照，后续改名或退馆不会影响历史消息。
type WorldMessage struct {
	ID            int64     `json:"id"`
	SenderID      string    `json:"sender_id"`
	SenderName    string    `json:"sender_name"`
	SenderAvatar  string    `json:"sender_avatar"`
	Content       string    `json:"content"`
	ContentFormat string    `json:"content_format"`
	ParentID      *int64    `json:"parent_id"`
	GuildID       string    `json:"guild_id"`
	GuildName     string    `json:"guild_name"`
	IsLeader      bool      `json:"is_leader"`
	IsAdmin       bool      `json:"is_admin"`
	AdminID       string    `json:"admin_id,omitempty"`
	CreatedAt     time.Time `json:"created_at"`
}

// WorldUserSnapshot 发言时的用户资料快照（会馆 ID 使用对外稳定 UUID）。
type WorldUserSnapshot struct {
	UserID    string
	Name      string
	Avatar    string
	GuildID   string
	GuildName string
	IsLeader  bool
}

// worldMessageColumns 查询列（NULL 统一 COALESCE，避免历史数据扫描失败）。
const worldMessageColumns = `id, sender_id, COALESCE(sender_name, ''), COALESCE(sender_avatar, ''),
	content, COALESCE(content_format, 'html'), parent_id, COALESCE(guild_id, ''), COALESCE(guild_name, ''),
	is_leader, is_admin, COALESCE(admin_id, ''), created_at`

// NormalizeWorldLimit 归一化列表条数：<=0 取默认 50，>500 截断为 500。
func NormalizeWorldLimit(limit int) int {
	switch {
	case limit <= 0:
		return WorldDefaultLimit
	case limit > WorldMaxLimit:
		return WorldMaxLimit
	default:
		return limit
	}
}

// NormalizeWorldCursors 归一化游标：负数视为未提供；before_id 与 after_id 同时给出时
// 以 after_id 优先（增量补发语义），before_id 置 0。
func NormalizeWorldCursors(beforeID, afterID int64) (int64, int64) {
	if beforeID < 0 {
		beforeID = 0
	}
	if afterID < 0 {
		afterID = 0
	}
	if beforeID > 0 && afterID > 0 {
		beforeID = 0
	}
	return beforeID, afterID
}

// ListWorldMessages 世界频道消息分页。
//   - after_id > 0：返回 id 之后的增量消息（升序，便于客户端追加）；
//   - before_id > 0：返回 id 之前的历史消息（降序，向上翻页）；
//   - 都未提供：返回最新一页（降序）。
//
// has_more 表示查询方向上还有更多数据（内部多取一条探测）。
func (d *DB) ListWorldMessages(ctx context.Context, beforeID, afterID int64, limit int) ([]WorldMessage, bool, error) {
	limit = NormalizeWorldLimit(limit)
	beforeID, afterID = NormalizeWorldCursors(beforeID, afterID)

	var (
		rows pgx.Rows
		err  error
	)
	switch {
	case afterID > 0:
		rows, err = d.Query(ctx, `SELECT `+worldMessageColumns+` FROM world_messages
			WHERE status = 1 AND id > $1 ORDER BY id ASC LIMIT $2`, afterID, limit+1)
	case beforeID > 0:
		rows, err = d.Query(ctx, `SELECT `+worldMessageColumns+` FROM world_messages
			WHERE status = 1 AND id < $1 ORDER BY id DESC LIMIT $2`, beforeID, limit+1)
	default:
		rows, err = d.Query(ctx, `SELECT `+worldMessageColumns+` FROM world_messages
			WHERE status = 1 ORDER BY id DESC LIMIT $1`, limit+1)
	}
	if err != nil {
		return nil, false, err
	}
	return scanWorldMessages(rows, limit)
}

// ListWorldAfterID 增量拉取 id 之后的消息（升序；供 poller / SSE 补发使用）。
func (d *DB) ListWorldAfterID(ctx context.Context, id int64, limit int) ([]WorldMessage, error) {
	if id < 0 {
		id = 0
	}
	limit = NormalizeWorldLimit(limit)
	rows, err := d.Query(ctx, `SELECT `+worldMessageColumns+` FROM world_messages
		WHERE status = 1 AND id > $1 ORDER BY id ASC LIMIT $2`, id, limit)
	if err != nil {
		return nil, err
	}
	items, _, err := scanWorldMessages(rows, limit)
	return items, err
}

func scanWorldMessages(rows pgx.Rows, limit int) ([]WorldMessage, bool, error) {
	defer rows.Close()
	items := []WorldMessage{}
	for rows.Next() {
		var m WorldMessage
		if err := rows.Scan(&m.ID, &m.SenderID, &m.SenderName, &m.SenderAvatar, &m.Content,
			&m.ContentFormat, &m.ParentID, &m.GuildID, &m.GuildName, &m.IsLeader, &m.IsAdmin,
			&m.AdminID, &m.CreatedAt); err != nil {
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

// GetWorldUserSnapshot 读取发送者昵称/头像与所在会馆快照；用户不存在返回 (nil, nil)。
// 会馆 ID 使用 guilds.uuid（对外稳定标识），未入馆时为空串。
func (d *DB) GetWorldUserSnapshot(ctx context.Context, userID string) (*WorldUserSnapshot, error) {
	var s WorldUserSnapshot
	err := d.QueryRow(ctx, `SELECT u.id, COALESCE(u.name, ''), COALESCE(u.avatar, ''),
		COALESCE(g.uuid::text, ''), COALESCE(g.name, ''),
		COALESCE(g.leader_user_id = u.id, FALSE)
		FROM users u
		LEFT JOIN guild_members gm ON gm.user_id = u.id
		LEFT JOIN guilds g ON g.id = gm.guild_id
		WHERE u.id = $1`, userID).
		Scan(&s.UserID, &s.Name, &s.Avatar, &s.GuildID, &s.GuildName, &s.IsLeader)
	if errors.Is(err, pgx.ErrNoRows) {
		return nil, nil
	}
	if err != nil {
		return nil, err
	}
	return &s, nil
}

// CreateWorldMessage 写入一条世界频道消息：
//   - 2 秒/用户限流（advisory lock 串行化同用户并发发送，避免并发绕过）；
//   - 快照 sender_name / sender_avatar / guild_id / guild_name / is_leader。
//
// 返回新消息 id；命中限流返回 ErrWorldRateLimited。
func (d *DB) CreateWorldMessage(ctx context.Context, userID, content, contentFormat string, parentID *int64) (int64, error) {
	snap, err := d.GetWorldUserSnapshot(ctx, userID)
	if err != nil {
		return 0, err
	}
	if snap == nil {
		return 0, ErrWorldUserNotFound
	}
	if contentFormat == "" {
		contentFormat = "html"
	}
	var id int64
	err = d.Tx(ctx, func(tx pgx.Tx) error {
		// 同用户串行化：并发请求均看到前一条已提交消息，2 秒限流才可靠。
		if _, err := tx.Exec(ctx, `SELECT pg_advisory_xact_lock(hashtext($1::varchar))`, "world_send:"+userID); err != nil {
			return err
		}
		// 以库内时钟为基准比较，避免应用/数据库时钟偏差导致误判。
		var (
			last  *time.Time
			dbNow time.Time
		)
		if err := tx.QueryRow(ctx, `SELECT MAX(created_at), NOW() FROM world_messages WHERE sender_id = $1`, userID).Scan(&last, &dbNow); err != nil {
			return err
		}
		if !worldSendAllowed(last, dbNow) {
			return ErrWorldRateLimited
		}
		if err := tx.QueryRow(ctx, `INSERT INTO world_messages
			(sender_id, sender_name, sender_avatar, content, content_format, parent_id, guild_id, guild_name, is_leader)
			VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9) RETURNING id`,
			userID, snap.Name, snap.Avatar, content, contentFormat, parentID,
			snap.GuildID, snap.GuildName, snap.IsLeader).Scan(&id); err != nil {
			return err
		}
		return syncMediaReferencesTx(ctx, tx, "world_message", strconv.FormatInt(id, 10), content)
	})
	if err != nil {
		return 0, err
	}
	return id, nil
}

// worldSendAllowed 距上次发言是否已满 2 秒（last 为空表示从未发言）。
func worldSendAllowed(last *time.Time, now time.Time) bool {
	if last == nil || last.IsZero() {
		return true
	}
	return now.Sub(*last) >= worldSendInterval
}

// worldCleanupCutoffOffset 计算 cutoff 的降序 OFFSET：恒为 keep（0 基），
// 即第 keep+1 新的那条消息；id <= cutoff 的行全部在保留窗口之外。
// total <= keep 时无需清理，返回 (0, false)。
func worldCleanupCutoffOffset(total, keep int64) (int64, bool) {
	if keep < 1 {
		keep = 1
	}
	if total <= keep {
		return 0, false
	}
	return keep, true
}

// WorldCleanup 清理世界频道历史消息：保留最新 WorldKeepCount 条，
// 计算 cutoff 后按 1000 条/批删除，advisory lock 防止多实例并发清理。
// 返回删除行数。
func (d *DB) WorldCleanup(ctx context.Context) (int64, error) {
	var deleted int64
	err := d.Tx(ctx, func(tx pgx.Tx) error {
		var locked bool
		if err := tx.QueryRow(ctx, `SELECT pg_try_advisory_xact_lock(hashtext($1::varchar))`, worldCleanupLockKey).Scan(&locked); err != nil {
			return err
		}
		if !locked {
			log.Printf("[WORLD] 清理任务已在其他实例执行，跳过本轮")
			return nil
		}

		var total int64
		if err := tx.QueryRow(ctx, `SELECT COUNT(*) FROM world_messages`).Scan(&total); err != nil {
			return err
		}
		offset, need := worldCleanupCutoffOffset(total, WorldKeepCount)
		if !need {
			return nil
		}
		// cutoff = 第 keep+1 新消息的 id；id <= cutoff 的行全部在保留窗口之外。
		var cutoffID int64
		if err := tx.QueryRow(ctx, `SELECT id FROM world_messages ORDER BY id DESC OFFSET $1 LIMIT 1`, offset).Scan(&cutoffID); err != nil {
			if errors.Is(err, pgx.ErrNoRows) {
				return nil
			}
			return err
		}

		for {
			tag, err := tx.Exec(ctx, `DELETE FROM world_messages WHERE id IN (
				SELECT id FROM world_messages WHERE id <= $1 ORDER BY id ASC LIMIT $2)`, cutoffID, worldCleanupBatchSize)
			if err != nil {
				return err
			}
			n := tag.RowsAffected()
			deleted += n
			if n < worldCleanupBatchSize {
				break
			}
			if err := ctx.Err(); err != nil {
				return err
			}
		}
		return nil
	})
	return deleted, err
}
