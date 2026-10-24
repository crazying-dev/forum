package database

import (
	"context"
	"errors"
	"log"
	"regexp"
	"time"

	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgconn"
)

// ---- 用户媒体（发帖图片）----

// MediaAsset 媒体资产行（服务端内部使用；上传响应只暴露 id 与 url）。
type MediaAsset struct {
	ID              string
	FileName        string
	OriginalName    string
	Mime            string
	Size            int64
	UploaderUserID  string
	UploaderAdminID string
	Scene           string
	Status          int
	StorageProvider string
	Bucket          string
	ObjectKey       string
	PublicURL       string
	OwnerType       string
	OwnerID         string
	GuildUUID       string
	Width           int
	Height          int
	SHA256          string
	Visibility      string
	IsLegacy        bool
	CreatedAt       *time.Time
	DeletedAt       *time.Time
}

// CreateMediaAssetInput 新建媒体资产。
type CreateMediaAssetInput struct {
	ID              string
	FileName        string
	OriginalName    string
	Mime            string
	Size            int64
	UploaderUserID  string
	UploaderAdminID string
	Scene           string
	StorageProvider string
	Bucket          string
	ObjectKey       string
	PublicURL       string
	OwnerType       string
	OwnerID         string
	GuildUUID       string
	Width           int
	Height          int
	SHA256          string
	Visibility      string
}

// CreateMediaAsset 记录新媒体资产（status=1 正常）。
func (d *DB) CreateMediaAsset(ctx context.Context, in CreateMediaAssetInput) error {
	return d.CreateMediaAssetWithVariants(ctx, in, nil)
}

// createMediaAssetTx 在事务内插入 media_assets 行。
func createMediaAssetTx(ctx context.Context, tx pgx.Tx, in CreateMediaAssetInput) error {
	_, err := tx.Exec(ctx, `INSERT INTO media_assets
		(id, file_name, original_name, mime, size, uploader_user_id, uploader_admin_id, scene, status,
		 storage_provider, bucket, object_key, public_url, owner_type, owner_id, guild_uuid,
		 width, height, sha256, visibility, is_legacy)
		VALUES ($1,NULLIF($2,''),$3,$4,$5,NULLIF($6,''),$7,$8,1,
		 $9,$10,$11,$12,$13,$14,$15,$16,$17,$18,$19,FALSE)`,
		in.ID, in.FileName, in.OriginalName, in.Mime, in.Size, in.UploaderUserID, in.UploaderAdminID,
		in.Scene, in.StorageProvider, in.Bucket, in.ObjectKey, in.PublicURL, in.OwnerType, in.OwnerID,
		in.GuildUUID, in.Width, in.Height, in.SHA256, in.Visibility)
	return err
}

// CreateMediaAssetWithVariants 同一事务写入媒体资产与变体（变体可为空），
// 保证不会出现“资产存在但变体缺失”的中间态。
func (d *DB) CreateMediaAssetWithVariants(ctx context.Context, in CreateMediaAssetInput, variants []MediaVariantInput) error {
	err := d.Tx(ctx, func(tx pgx.Tx) error {
		if err := createMediaAssetTx(ctx, tx, in); err != nil {
			return err
		}
		for _, v := range variants {
			if _, err := tx.Exec(ctx, `INSERT INTO media_variants
				(media_id, variant, object_key, bucket, mime, width, height, size, sha256)
				VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9)`,
				in.ID, v.Variant, v.ObjectKey, v.Bucket, v.Mime, v.Width, v.Height, v.Size, v.SHA256); err != nil {
				return err
			}
		}
		return nil
	})
	// 迁移 0028 未执行时（media_variants 不存在）不能让整个上传失败：
	// 回滚事务后只写资产行并告警，原图仍可用，变体可在迁移后回填。
	if err != nil && len(variants) > 0 && isUndefinedTable(err) {
		log.Printf("[WARN] media_variants 表不存在，本次仅写资产（请尽快执行迁移 0028）: %v", err)
		return d.CreateMediaAsset(ctx, in)
	}
	return err
}

// isUndefinedTable 判断是否为 PostgreSQL 42P01（表不存在）。
func isUndefinedTable(err error) bool {
	var pgErr *pgconn.PgError
	return errors.As(err, &pgErr) && pgErr.Code == "42P01"
}

// MediaVariant 媒体变体行（上传时预生成的等比缩放图；仅 S3 媒体）。
type MediaVariant struct {
	MediaID   string
	Variant   string // w480 / w1280
	ObjectKey string
	Bucket    string
	Mime      string
	Width     int
	Height    int
	Size      int64
	SHA256    string
	CreatedAt *time.Time
}

// MediaVariantInput 新建变体输入（media_id 由所属资产决定）。
type MediaVariantInput struct {
	Variant   string
	ObjectKey string
	Bucket    string
	Mime      string
	Width     int
	Height    int
	Size      int64
	SHA256    string
}

// GetMediaVariant 读取单个变体；不存在返回 (nil, nil)。
func (d *DB) GetMediaVariant(ctx context.Context, mediaID, variant string) (*MediaVariant, error) {
	var v MediaVariant
	err := d.QueryRow(ctx, `SELECT media_id, variant, object_key, bucket, mime, width, height, size, sha256, created_at
		FROM media_variants WHERE media_id = $1 AND variant = $2`, mediaID, variant).
		Scan(&v.MediaID, &v.Variant, &v.ObjectKey, &v.Bucket, &v.Mime, &v.Width, &v.Height, &v.Size, &v.SHA256, &v.CreatedAt)
	if errors.Is(err, pgx.ErrNoRows) {
		return nil, nil
	}
	if err != nil {
		return nil, err
	}
	return &v, nil
}

// ListMediaVariants 读取某媒体的全部变体（按 variant 升序）。
func (d *DB) ListMediaVariants(ctx context.Context, mediaID string) ([]MediaVariant, error) {
	rows, err := d.Query(ctx, `SELECT media_id, variant, object_key, bucket, mime, width, height, size, sha256, created_at
		FROM media_variants WHERE media_id = $1 ORDER BY variant`, mediaID)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	out := []MediaVariant{}
	for rows.Next() {
		var v MediaVariant
		if err := rows.Scan(&v.MediaID, &v.Variant, &v.ObjectKey, &v.Bucket, &v.Mime, &v.Width, &v.Height, &v.Size, &v.SHA256, &v.CreatedAt); err != nil {
			return nil, err
		}
		out = append(out, v)
	}
	return out, rows.Err()
}

// MarkMediaGCed 物理对象删除成功后标记该资产已回收（gc_state=2），并清理变体行；
// 事务失败只影响下次重试，不影响已删除的对象。
func (d *DB) MarkMediaGCed(ctx context.Context, mediaID string) error {
	return d.Tx(ctx, func(tx pgx.Tx) error {
		if _, err := tx.Exec(ctx, `UPDATE media_assets SET gc_state = 2 WHERE id = $1`, mediaID); err != nil {
			return err
		}
		var hasVariants bool
		if err := tx.QueryRow(ctx, `SELECT to_regclass('public.media_variants') IS NOT NULL`).Scan(&hasVariants); err != nil {
			return err
		}
		if hasVariants {
			if _, err := tx.Exec(ctx, `DELETE FROM media_variants WHERE media_id = $1`, mediaID); err != nil {
				return err
			}
		}
		return nil
	})
}

// GetMediaAsset 读取可用图片资产（status=1）；不存在或已删除返回 (nil, nil)。
func (d *DB) GetMediaAsset(ctx context.Context, id string) (*MediaAsset, error) {
	var m MediaAsset
	err := d.QueryRow(ctx, `SELECT id, COALESCE(file_name,''), original_name, mime, size,
		COALESCE(uploader_user_id,''), uploader_admin_id, scene, status,
		storage_provider, bucket, object_key, public_url, owner_type, owner_id, guild_uuid,
		width, height, sha256, visibility, is_legacy, created_at, deleted_at
		FROM media_assets WHERE id = $1 AND status = 1`, id).
		Scan(&m.ID, &m.FileName, &m.OriginalName, &m.Mime, &m.Size,
			&m.UploaderUserID, &m.UploaderAdminID, &m.Scene, &m.Status,
			&m.StorageProvider, &m.Bucket, &m.ObjectKey, &m.PublicURL, &m.OwnerType, &m.OwnerID, &m.GuildUUID,
			&m.Width, &m.Height, &m.SHA256, &m.Visibility, &m.IsLegacy, &m.CreatedAt, &m.DeletedAt)
	if errors.Is(err, pgx.ErrNoRows) {
		return nil, nil
	}
	if err != nil {
		return nil, err
	}
	return &m, nil
}

var mediaRefRe = regexp.MustCompile(`/(?:ov2/api|api/v1)/media/(MD[0-9a-fA-F]{16,})`)

// ExtractMediaIDs 从富文本中提取 ouo 媒体 ID（去重、保序）。
func ExtractMediaIDs(content string) []string {
	matches := mediaRefRe.FindAllStringSubmatch(content, -1)
	seen := map[string]struct{}{}
	out := make([]string, 0, len(matches))
	for _, m := range matches {
		id := m[1]
		if _, ok := seen[id]; ok {
			continue
		}
		seen[id] = struct{}{}
		out = append(out, id)
	}
	return out
}

// syncMediaReferencesTx 重建某个内容所有者的媒体引用（同事务）。
func syncMediaReferencesTx(ctx context.Context, tx pgx.Tx, ownerType, ownerID, content string) error {
	if ownerType == "" || ownerID == "" {
		return nil
	}
	if _, err := tx.Exec(ctx, `DELETE FROM media_references WHERE owner_type = $1 AND owner_id = $2`, ownerType, ownerID); err != nil {
		return err
	}
	for _, id := range ExtractMediaIDs(content) {
		if _, err := tx.Exec(ctx, `INSERT INTO media_references (media_id, owner_type, owner_id)
			VALUES ($1,$2,$3) ON CONFLICT DO NOTHING`, id, ownerType, ownerID); err != nil {
			return err
		}
	}
	return nil
}

// softDeleteUnreferencedMediaTx 内容删除时：仅对“已无任何引用”的新媒体置 status=0，并移除该内容引用。
// 旧媒体（is_legacy=TRUE）永不在这里删除。
func softDeleteUnreferencedMediaTx(ctx context.Context, tx pgx.Tx, ownerType, ownerID string) error {
	if ownerType == "" || ownerID == "" {
		return nil
	}
	rows, err := tx.Query(ctx, `SELECT media_id FROM media_references WHERE owner_type = $1 AND owner_id = $2`, ownerType, ownerID)
	if err != nil {
		return err
	}
	ids := make([]string, 0, 4)
	for rows.Next() {
		var id string
		if err := rows.Scan(&id); err != nil {
			rows.Close()
			return err
		}
		ids = append(ids, id)
	}
	if err := rows.Err(); err != nil {
		rows.Close()
		return err
	}
	rows.Close()
	if _, err := tx.Exec(ctx, `DELETE FROM media_references WHERE owner_type = $1 AND owner_id = $2`, ownerType, ownerID); err != nil {
		return err
	}
	if len(ids) == 0 {
		return nil
	}
	// 删除引用后（同事务）再判断“是否仍被其他内容引用”，只失效无人引用的新媒体。
	_, err = tx.Exec(ctx, `UPDATE media_assets SET status = 0, deleted_at = now()
		WHERE is_legacy = FALSE AND id = ANY($1)
		  AND NOT EXISTS (SELECT 1 FROM media_references mr WHERE mr.media_id = media_assets.id)`, ids)
	return err
}

// IsChatRoomMember 判断用户是否为聊天室成员（私密图片 ACL）。
func (d *DB) IsChatRoomMember(ctx context.Context, roomID, userID string) (bool, error) {
	var ok bool
	err := d.QueryRow(ctx, `SELECT EXISTS(
		SELECT 1 FROM chat_members cm JOIN chat_rooms cr ON cr.id = cm.room_id
		WHERE cm.room_id = $1 AND cm.member_type = 'user' AND cm.member_id = $2
	)`, roomID, userID).Scan(&ok)
	return ok, err
}

// GetPostOwnerAndPublished 读取帖子作者与发布时间（私密/定时帖图片 ACL）。
func (d *DB) GetPostOwnerAndPublished(ctx context.Context, postID string) (string, *time.Time, error) {
	var userID string
	var publishedAt *time.Time
	err := d.QueryRow(ctx, `SELECT user_id, published_at FROM posts WHERE id = $1`, postID).Scan(&userID, &publishedAt)
	if errors.Is(err, pgx.ErrNoRows) {
		return "", nil, nil
	}
	return userID, publishedAt, err
}

// GetCommentOwner 读取评论作者（私密评论图片 ACL）。
func (d *DB) GetCommentOwner(ctx context.Context, commentID string) (string, error) {
	var userID string
	err := d.QueryRow(ctx, `SELECT user_id FROM comments WHERE id = $1`, commentID).Scan(&userID)
	if errors.Is(err, pgx.ErrNoRows) {
		return "", nil
	}
	return userID, err
}

// ListExpiredMediaAssets 待清理的已删除图片（status=0、deleted_at 早于 days 天前、且尚未 GC）；
// 行记录保留，成功后由 MarkMediaGCed 置 gc_state=2，避免每小时重复处理历史资产。
// 仍被 media_references 引用的资产永不返回（与下方 NOT EXISTS 守卫一致）；
// media_references 表缺失时无法判断引用，跳过本轮清理。
func (d *DB) ListExpiredMediaAssets(ctx context.Context, days int) ([]MediaAsset, error) {
	if days < 1 {
		days = 7
	}
	var refsExists bool
	if err := d.QueryRow(ctx, `SELECT to_regclass('public.media_references') IS NOT NULL`).Scan(&refsExists); err != nil {
		return nil, err
	}
	if !refsExists {
		log.Printf("[WARN] media_references 表不存在，跳过本轮过期媒体清理")
		return []MediaAsset{}, nil
	}
	rows, err := d.Query(ctx, `SELECT id, COALESCE(file_name,''), mime, storage_provider, bucket, object_key, is_legacy
		FROM media_assets
		WHERE status = 0 AND deleted_at IS NOT NULL AND deleted_at < now() - $1 * INTERVAL '1 day'
		  AND COALESCE(gc_state, 0) = 0
		  AND NOT EXISTS (SELECT 1 FROM media_references mr WHERE mr.media_id = media_assets.id)
		ORDER BY deleted_at ASC
		LIMIT 200`, days)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	assets := []MediaAsset{}
	for rows.Next() {
		var m MediaAsset
		if err := rows.Scan(&m.ID, &m.FileName, &m.Mime, &m.StorageProvider, &m.Bucket, &m.ObjectKey, &m.IsLegacy); err != nil {
			return nil, err
		}
		assets = append(assets, m)
	}
	return assets, rows.Err()
}
