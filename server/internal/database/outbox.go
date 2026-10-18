package database

import (
	"context"
	"errors"
	"fmt"
	"strings"
	"time"

	"github.com/jackc/pgx/v5"
)

// email_outbox.status
const (
	EmailStatusPending = 0
	EmailStatusSending = 1
	EmailStatusSent    = 2
	EmailStatusDead    = 3
)

// email_fanout_jobs.status
const (
	FanoutStatusPending    = 0
	FanoutStatusProcessing = 1
	FanoutStatusDone       = 2
	FanoutStatusDead       = 3
)

// EmailOutboxInput 邮件 outbox 入队参数。To 中每个收件人落一行，避免 To: 泄露。
type EmailOutboxInput struct {
	To          []string
	Subject     string
	PlainBody   string
	HTMLBody    string
	DedupeKey   string
	ScheduledAt *time.Time
}

// EnqueueEmailTx 在事务内按收件人逐行入队（dedupe_key 幂等）。返回实际插入行数。
func (d *DB) EnqueueEmailTx(ctx context.Context, tx pgx.Tx, in EmailOutboxInput) (int, error) {
	if strings.TrimSpace(in.Subject) == "" {
		return 0, fmt.Errorf("outbox: subject 不能为空")
	}
	if in.ScheduledAt == nil {
		now := time.Now().UTC()
		in.ScheduledAt = &now
	}
	seen := make(map[string]struct{}, len(in.To))
	inserted := 0
	for _, raw := range in.To {
		to := strings.TrimSpace(raw)
		if to == "" || !strings.Contains(to, "@") {
			continue
		}
		if _, ok := seen[strings.ToLower(to)]; ok {
			continue
		}
		seen[strings.ToLower(to)] = struct{}{}

		key := strings.TrimSpace(in.DedupeKey)
		if key != "" && len(in.To) > 1 {
			// 一邮多收：dedupe 后缀收件人，避免第二行被唯一索引吃掉
			key = key + ":" + to
		}
		key = normalizeDedupeKey(key)

		tag, err := tx.Exec(ctx, `INSERT INTO email_outbox
			(to_email, subject, plain_body, html_body, dedupe_key, scheduled_at)
			VALUES ($1, $2, $3, $4, $5, $6)
			ON CONFLICT (dedupe_key) WHERE dedupe_key <> '' DO NOTHING`,
			to, in.Subject, in.PlainBody, in.HTMLBody, key, *in.ScheduledAt)
		if err != nil {
			return inserted, err
		}
		inserted += int(tag.RowsAffected())
	}
	return inserted, nil
}

// EnqueueEmail 非事务便捷入口。
func (d *DB) EnqueueEmail(ctx context.Context, in EmailOutboxInput) (int, error) {
	inserted := 0
	err := d.Tx(ctx, func(tx pgx.Tx) error {
		var e error
		inserted, e = d.EnqueueEmailTx(ctx, tx, in)
		return e
	})
	return inserted, err
}

// EnqueueFanoutTx 入队粉丝邮件 fanout job（kind=follower_post；同帖幂等）。
func (d *DB) EnqueueFanoutTx(ctx context.Context, tx pgx.Tx, postID, actorID string) (bool, error) {
	if postID == "" {
		return false, fmt.Errorf("fanout: post_id 不能为空")
	}
	tag, err := tx.Exec(ctx, `INSERT INTO email_fanout_jobs (kind, ref_id, actor_id)
		VALUES ('follower_post', $1, $2)
		ON CONFLICT (kind, ref_id) DO NOTHING`, postID, actorID)
	if err != nil {
		return false, err
	}
	return tag.RowsAffected() > 0, nil
}

// EnqueueFanout 非事务便捷入口。
func (d *DB) EnqueueFanout(ctx context.Context, postID, actorID string) (bool, error) {
	var created bool
	err := d.Tx(ctx, func(tx pgx.Tx) error {
		var e error
		created, e = d.EnqueueFanoutTx(ctx, tx, postID, actorID)
		return e
	})
	return created, err
}

// OutboxEmail 已认领（status=1）待发送的邮件。
type OutboxEmail struct {
	ID        int64
	ToEmail   string
	Subject   string
	PlainBody string
	HTMLBody  string
	Attempts  int
}

// ClaimEmailBatch 原子认领至多 limit 条到期待发邮件（SKIP LOCKED，多实例安全），status 置 1、attempts+1。
func (d *DB) ClaimEmailBatch(ctx context.Context, limit int) ([]OutboxEmail, error) {
	limit = normalizeLimit(limit, 20, 100)
	rows, err := d.Query(ctx, `
		WITH claimed AS (
			SELECT id FROM email_outbox
			WHERE status = 0 AND scheduled_at <= NOW()
			ORDER BY scheduled_at, id
			LIMIT $1
			FOR UPDATE SKIP LOCKED
		)
		UPDATE email_outbox o
		SET status = 1, attempts = o.attempts + 1
		FROM claimed
		WHERE o.id = claimed.id
		RETURNING o.id, o.to_email, o.subject, o.plain_body, o.html_body, o.attempts`, limit)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	items := []OutboxEmail{}
	for rows.Next() {
		var e OutboxEmail
		if err := rows.Scan(&e.ID, &e.ToEmail, &e.Subject, &e.PlainBody, &e.HTMLBody, &e.Attempts); err != nil {
			return nil, err
		}
		items = append(items, e)
	}
	return items, rows.Err()
}

// MarkEmailSent 标记发送成功。
func (d *DB) MarkEmailSent(ctx context.Context, id int64) error {
	_, err := d.Exec(ctx, `UPDATE email_outbox
		SET status = 2, sent_at = NOW(), last_error = ''
		WHERE id = $1`, id)
	return err
}

// MarkEmailFailed 标记发送失败：retryAt 为零值视为死信（status=3），否则回到 pending 并按 retryAt 重试。
func (d *DB) MarkEmailFailed(ctx context.Context, id int64, lastError string, retryAt time.Time) error {
	lastError = truncateText(lastError, 2000)
	if retryAt.IsZero() {
		_, err := d.Exec(ctx, `UPDATE email_outbox SET status = 3, last_error = $2 WHERE id = $1`, id, lastError)
		return err
	}
	_, err := d.Exec(ctx, `UPDATE email_outbox
		SET status = 0, scheduled_at = $3, last_error = $2
		WHERE id = $1`, id, lastError, retryAt)
	return err
}

// FanoutJob 已认领的 fanout job。
type FanoutJob struct {
	ID       int64
	Kind     string
	RefID    string
	ActorID  string
	Attempts int
}

// ClaimFanoutJobs 原子认领待处理 fanout job（SKIP LOCKED），status 置 1、attempts+1。
func (d *DB) ClaimFanoutJobs(ctx context.Context, limit int) ([]FanoutJob, error) {
	limit = normalizeLimit(limit, 10, 50)
	rows, err := d.Query(ctx, `
		WITH claimed AS (
			SELECT id FROM email_fanout_jobs
			WHERE status = 0
			ORDER BY created_at, id
			LIMIT $1
			FOR UPDATE SKIP LOCKED
		)
		UPDATE email_fanout_jobs j
		SET status = 1, attempts = j.attempts + 1
		FROM claimed
		WHERE j.id = claimed.id
		RETURNING j.id, j.kind, j.ref_id, j.actor_id, j.attempts`, limit)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	items := []FanoutJob{}
	for rows.Next() {
		var j FanoutJob
		if err := rows.Scan(&j.ID, &j.Kind, &j.RefID, &j.ActorID, &j.Attempts); err != nil {
			return nil, err
		}
		items = append(items, j)
	}
	return items, rows.Err()
}

// MarkFanoutDone 完成 fanout job；lastError 非空视为失败，attempts>=5 进死信。
func (d *DB) MarkFanoutDone(ctx context.Context, id int64, lastError string) error {
	lastError = truncateText(lastError, 2000)
	_, err := d.Exec(ctx, `UPDATE email_fanout_jobs
		SET last_error = $2,
			status = CASE WHEN $2 = '' THEN 2 WHEN attempts >= 5 THEN 3 ELSE 0 END,
			processed_at = CASE WHEN $2 = '' OR attempts >= 5 THEN NOW() ELSE NULL END
		WHERE id = $1`, id, lastError)
	return err
}

// ListFollowerEmails 粉丝邮箱（过滤封禁/注销/未验证/空邮箱）。
func (d *DB) ListFollowerEmails(ctx context.Context, userID string, limit int) ([]string, error) {
	limit = normalizeLimit(limit, 1000, 5000)
	rows, err := d.Query(ctx, `SELECT DISTINCT u.email
		FROM user_follows f JOIN users u ON u.id = f.follower_id
		WHERE f.following_id = $1
			AND u.is_banned = 0
			AND u.deleted_at IS NULL
			AND u.email_verified = 1
			AND u.email <> ''
		LIMIT $2`, userID, limit)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	emails := []string{}
	for rows.Next() {
		var e string
		if err := rows.Scan(&e); err != nil {
			return nil, err
		}
		emails = append(emails, e)
	}
	return emails, rows.Err()
}

// FanoutPost 粉丝发帖邮件所需信息。
type FanoutPost struct {
	ID         string
	Title      string
	AuthorID   string
	AuthorName string
}

// GetFanoutPost 读取已发布的帖子信息（供 fanout 展开邮件文案）。
func (d *DB) GetFanoutPost(ctx context.Context, postID string) (*FanoutPost, error) {
	var p FanoutPost
	err := d.QueryRow(ctx, `SELECT p.id, p.title, p.user_id, COALESCE(u.name, '')
		FROM posts p JOIN users u ON u.id = p.user_id
		WHERE p.id = $1 AND p.status = 1`, postID).Scan(&p.ID, &p.Title, &p.AuthorID, &p.AuthorName)
	if errors.Is(err, pgx.ErrNoRows) {
		return nil, nil
	}
	if err != nil {
		return nil, err
	}
	return &p, nil
}

// truncateText 按字节截断错误信息，避免超出 TEXT 展示预期。
func truncateText(s string, max int) string {
	if len(s) <= max {
		return s
	}
	return s[:max]
}
