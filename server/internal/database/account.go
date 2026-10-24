package database

import (
	"context"
	"crypto/rand"
	"encoding/hex"
	"errors"
	"time"

	"github.com/jackc/pgx/v5"
	"golang.org/x/crypto/bcrypt"
)

// ---- 账号注销 ----

// AnonymizeUser 匿名化注销：保留帖子/评论/点赞/收藏/媒体等内容关联，抹去身份信息并禁止登录；
// defaultAvatar 由调用方按站点配置拼接；返回旧头像供调用方删除文件。
func (d *DB) AnonymizeUser(ctx context.Context, userID, defaultAvatar string) (string, error) {
	var oldAvatar, oldEmail string
	err := d.Tx(ctx, func(tx pgx.Tx) error {
		if err := tx.QueryRow(ctx, `SELECT email, COALESCE(avatar, '') FROM users WHERE id=$1`, userID).
			Scan(&oldEmail, &oldAvatar); err != nil {
			return err
		}
		// 随机密码哈希：使旧密码失效且不保留任何可推导信息
		raw := make([]byte, 32)
		if _, err := rand.Read(raw); err != nil {
			return err
		}
		hash, err := bcrypt.GenerateFromPassword([]byte(hex.EncodeToString(raw)), bcrypt.DefaultCost)
		if err != nil {
			return err
		}
		if _, err := tx.Exec(ctx, `UPDATE users SET name='已注销账户', email='deleted+'||id||'@deleted.invalid', avatar=$2,
			password=$3, gender=0, age='', intro='', prefix='', spirit=0, email_verified=0, deleted_at=NOW()
			WHERE id=$1`, userID, defaultAvatar, string(hash)); err != nil {
			return err
		}
		for _, q := range []string{
			`DELETE FROM sessions WHERE user_id=$1`,
			`DELETE FROM verify_tokens WHERE user_id=$1`,
			`DELETE FROM user_follows WHERE follower_id=$1 OR following_id=$1`,
			`DELETE FROM guild_members WHERE user_id=$1`,
			`DELETE FROM guild_join_requests WHERE user_id=$1`,
			`UPDATE guilds SET leader_user_id=NULL WHERE leader_user_id=$1`,
			`DELETE FROM email_change_requests WHERE user_id=$1`,
		} {
			if _, err := tx.Exec(ctx, q, userID); err != nil {
				return err
			}
		}
		if _, err := tx.Exec(ctx, `DELETE FROM verify_codes WHERE email=$1`, oldEmail); err != nil {
			return err
		}
		// 原邮箱的限流记录一并清除（邮箱释放后重新注册不应受旧记录影响）
		if _, err := tx.Exec(ctx, `DELETE FROM account_action_limits WHERE email=$1`, oldEmail); err != nil {
			return err
		}
		return nil
	})
	if err != nil {
		return "", err
	}
	return oldAvatar, nil
}

// PurgeUser 彻底注销：显式清理无外键关联的数据，最后删除 users 行（其余经外键级联清除）；返回旧头像。
func (d *DB) PurgeUser(ctx context.Context, userID string) (string, error) {
	var oldAvatar, oldEmail string
	err := d.Tx(ctx, func(tx pgx.Tx) error {
		if err := tx.QueryRow(ctx, `SELECT email, COALESCE(avatar, '') FROM users WHERE id=$1`, userID).
			Scan(&oldEmail, &oldAvatar); err != nil {
			return err
		}
		// 先清理该用户帖子/评论产生的媒体引用：下面会级联删除 posts/comments，
		// media_references 无外键不会自动清，残留引用会把媒体永久钉住（无法 GC，公开图仍可被访问）。
		if _, err := tx.Exec(ctx, `DELETE FROM media_references
			WHERE (owner_type = 'post' AND owner_id IN (SELECT id FROM posts WHERE user_id=$1))
			   OR (owner_type = 'comment' AND owner_id IN (SELECT id FROM comments WHERE user_id=$1))`, userID); err != nil {
			return err
		}
		// media_assets 仅置为已删除，物理文件交由后台过期媒体清理任务处理；
		// 仍被 media_references 引用的资产保持 status=1，避免误删其他内容仍在用的图片。
		if _, err := tx.Exec(ctx, `UPDATE media_assets SET status=0, deleted_at=NOW()
			WHERE uploader_user_id=$1
			  AND NOT EXISTS (SELECT 1 FROM media_references mr WHERE mr.media_id = media_assets.id)`, userID); err != nil {
			return err
		}
		// bug_report_logs 与 bug_reports 无外键关联，需先删日志再删报告
		if _, err := tx.Exec(ctx, `DELETE FROM bug_report_logs WHERE report_id IN (SELECT id FROM bug_reports WHERE reporter_id=$1)`, userID); err != nil {
			return err
		}
		if _, err := tx.Exec(ctx, `DELETE FROM bug_reports WHERE reporter_id=$1`, userID); err != nil {
			return err
		}
		if _, err := tx.Exec(ctx, `DELETE FROM version_votes WHERE voter_id=$1`, userID); err != nil {
			return err
		}
		if _, err := tx.Exec(ctx, `DELETE FROM verify_codes WHERE email=$1`, oldEmail); err != nil {
			return err
		}
		if _, err := tx.Exec(ctx, `DELETE FROM guild_articles WHERE author_user_id=$1`, userID); err != nil {
			return err
		}
		if _, err := tx.Exec(ctx, `DELETE FROM email_change_requests WHERE user_id=$1`, userID); err != nil {
			return err
		}
		// 点赞计数回补：级联删除 post_likes/comment_likes 前，先修正他人帖子/评论上的冗余计数
		if _, err := tx.Exec(ctx, `UPDATE posts SET likes = GREATEST(likes - sub.cnt, 0)
			FROM (SELECT post_id, COUNT(*) AS cnt FROM post_likes WHERE user_id=$1 GROUP BY post_id) AS sub
			WHERE posts.id = sub.post_id`, userID); err != nil {
			return err
		}
		if _, err := tx.Exec(ctx, `UPDATE comments SET likes = GREATEST(likes - sub.cnt, 0)
			FROM (SELECT comment_id, COUNT(*) AS cnt FROM comment_likes WHERE user_id=$1 GROUP BY comment_id) AS sub
			WHERE comments.id = sub.comment_id`, userID); err != nil {
			return err
		}
		// 原邮箱的限流记录一并清除
		if _, err := tx.Exec(ctx, `DELETE FROM account_action_limits WHERE email=$1`, oldEmail); err != nil {
			return err
		}
		if _, err := tx.Exec(ctx, `DELETE FROM users WHERE id=$1`, userID); err != nil {
			return err
		}
		return nil
	})
	if err != nil {
		return "", err
	}
	return oldAvatar, nil
}

// ---- 邮箱换绑 ----

// EmailChangeRequest 邮箱换绑请求（stage 1=待验证当前邮箱 / 2=待验证新邮箱）。
type EmailChangeRequest struct {
	UserID        string
	OldEmail      string
	NewEmail      string
	Stage         int
	OldVerifiedAt *time.Time
	ExpiresAt     time.Time
	CreatedAt     time.Time
}

// UpsertEmailChangeRequest 创建或重置邮箱换绑请求（stage=1，待验证当前邮箱）。
func (d *DB) UpsertEmailChangeRequest(ctx context.Context, userID, oldEmail string, expiresMinutes int) error {
	if expiresMinutes <= 0 {
		expiresMinutes = 30
	}
	_, err := d.Exec(ctx, `INSERT INTO email_change_requests (user_id, old_email, expires_at)
		VALUES ($1,$2, NOW() + $3 * INTERVAL '1 minute')
		ON CONFLICT (user_id) DO UPDATE SET stage=1, new_email='', old_verified_at=NULL, expires_at=EXCLUDED.expires_at`,
		userID, oldEmail, expiresMinutes)
	return err
}

// GetEmailChangeRequest 读取换绑请求（不存在返回 nil, nil）。
func (d *DB) GetEmailChangeRequest(ctx context.Context, userID string) (*EmailChangeRequest, error) {
	var r EmailChangeRequest
	err := d.QueryRow(ctx, `SELECT user_id, old_email, new_email, stage, old_verified_at, expires_at, created_at
		FROM email_change_requests WHERE user_id=$1`, userID).
		Scan(&r.UserID, &r.OldEmail, &r.NewEmail, &r.Stage, &r.OldVerifiedAt, &r.ExpiresAt, &r.CreatedAt)
	if errors.Is(err, pgx.ErrNoRows) {
		return nil, nil
	}
	if err != nil {
		return nil, err
	}
	return &r, nil
}

// MarkOldEmailVerified 当前邮箱验证通过：进入 stage=2，请求有效期重置为 30 分钟。
func (d *DB) MarkOldEmailVerified(ctx context.Context, userID string) error {
	_, err := d.Exec(ctx, `UPDATE email_change_requests SET stage=2, old_verified_at=NOW(), expires_at=NOW() + INTERVAL '30 minutes'
		WHERE user_id=$1`, userID)
	return err
}

// SetNewEmail 记录待验证的新邮箱。
func (d *DB) SetNewEmail(ctx context.Context, userID, newEmail string) error {
	_, err := d.Exec(ctx, `UPDATE email_change_requests SET new_email=$2 WHERE user_id=$1`, userID, newEmail)
	return err
}

// DeleteEmailChangeRequest 删除换绑请求（换绑完成或重新发起前清理）。
func (d *DB) DeleteEmailChangeRequest(ctx context.Context, userID string) error {
	_, err := d.Exec(ctx, `DELETE FROM email_change_requests WHERE user_id=$1`, userID)
	return err
}
