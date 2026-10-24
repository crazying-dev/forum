// Package media 统一媒体保存/读取（SeaweedFS S3 / 旧本地目录）。
package media

import (
	"bytes"
	"context"
	"crypto/sha256"
	"encoding/hex"
	"errors"
	"fmt"
	"image"
	"image/jpeg"
	"image/png"
	"io"
	"io/fs"
	"log"
	"strings"
	"time"

	_ "golang.org/x/image/webp"
	_ "image/gif" // 注册 gif 解码

	"yj-forum/server/internal/database"
	"yj-forum/server/internal/storage"
)

const (
	MaxInputBytes = 5 << 20
	MaxPixels     = 12_000_000

	// cacheControlImmutable 媒体对象缓存策略：对象 key 含随机 ID，内容不变更。
	cacheControlImmutable = "public, max-age=31536000, immutable"
)

// ErrMediaNotFound 媒体字节不存在（数据库有记录但对象/文件缺失）。
var ErrMediaNotFound = errors.New("媒体不存在")

// decodeSem 限制并发解码量：大图解码占用内存高，避免上传洪峰打爆内存（容量 4）。
var decodeSem = make(chan struct{}, 4)

// Service 媒体服务。
type Service struct {
	DB     *database.DB
	S3     *storage.S3Provider
	Local  *storage.LocalProvider
	Bucket string
	// VariantsEnabled 上传时是否预生成 w480/w1280 变体（仅 S3 模式生效）。
	VariantsEnabled bool
}

// NewService 创建媒体服务；s3 为 nil 时回退本地目录。
func NewService(db *database.DB, s3 *storage.S3Provider, localDir, bucket string, variantsEnabled bool) *Service {
	return &Service{DB: db, S3: s3, Local: &storage.LocalProvider{Dir: localDir}, Bucket: bucket, VariantsEnabled: variantsEnabled}
}

// SaveInput 保存媒体输入。
type SaveInput struct {
	Data            []byte
	OriginalName    string
	Scene           string
	OwnerType       string
	OwnerID         string
	GuildUUID       string
	UploaderUserID  string
	UploaderAdminID string
	Visibility      string
	MaxBytes        int64 // 0 = MaxInputBytes（5MB）；头像可传 10MB
}

// Save 校验、重编码（JPEG/PNG）并保存到 S3/本地，返回资产。
// S3 模式下同时生成并写入变体（w480/w1280）；变体生成失败只记日志，不阻断上传。
func (s *Service) Save(ctx context.Context, in SaveInput) (*database.MediaAsset, error) {
	if len(in.Data) == 0 {
		return nil, fmt.Errorf("文件为空")
	}
	maxBytes := in.MaxBytes
	if maxBytes <= 0 {
		maxBytes = MaxInputBytes
	}
	if int64(len(in.Data)) > maxBytes {
		return nil, fmt.Errorf("图片超过大小上限")
	}
	ext, mime := sniffExt(in.Data)
	if ext == "" {
		return nil, fmt.Errorf("仅支持 PNG/JPG/WebP/GIF 图片")
	}
	id, err := database.GenMediaID()
	if err != nil {
		return nil, err
	}
	scene := strings.Trim(strings.TrimSpace(in.Scene), "/")
	if scene == "" {
		scene = "misc"
	}
	dir := time.Now().Format("2006/01")

	// 解码与变体缩放共用同一信号量：避免解码后的大图在信号量外长期占用内存。
	data, mime, width, height, variants, err := s.prepareUpload(ctx, in.Data, ext, mime, id, scene, dir)
	if err != nil {
		return nil, err
	}
	if int64(len(data)) > maxBytes {
		return nil, fmt.Errorf("图片处理后超过大小上限")
	}

	digest := sha256.Sum256(data)
	provider, key, fileName := "local", id+ext, id+ext
	publicURL := "/ov2/api/media/" + id

	if s.S3 != nil {
		provider = "s3"
		key = scene + "/" + dir + "/" + id + ext
		fileName = ""
	}

	if err := s.putObject(ctx, provider, key, data, mime); err != nil {
		return nil, err
	}
	written := []string{key}
	variantInputs := make([]database.MediaVariantInput, 0, len(variants))
	for _, v := range variants {
		if err := s.S3.Put(ctx, v.ObjectKey, v.Data, v.Mime, cacheControlImmutable); err != nil {
			s.rollbackObjects(written)
			return nil, fmt.Errorf("S3 变体保存失败: %w", err)
		}
		written = append(written, v.ObjectKey)
		variantInputs = append(variantInputs, database.MediaVariantInput{
			Variant: v.Variant, ObjectKey: v.ObjectKey, Bucket: s.Bucket, Mime: v.Mime,
			Width: v.Width, Height: v.Height, Size: int64(len(v.Data)), SHA256: v.SHA256,
		})
	}

	visibility := strings.TrimSpace(in.Visibility)
	if visibility == "" {
		visibility = "private"
	}
	assetInput := database.CreateMediaAssetInput{
		ID: id, FileName: fileName, OriginalName: truncate(in.OriginalName, 255), Mime: mime,
		Size: int64(len(data)), UploaderUserID: in.UploaderUserID, UploaderAdminID: in.UploaderAdminID,
		Scene: scene, StorageProvider: provider, Bucket: s.Bucket, ObjectKey: key, PublicURL: publicURL,
		OwnerType: in.OwnerType, OwnerID: in.OwnerID, GuildUUID: in.GuildUUID,
		Width: width, Height: height, SHA256: hex.EncodeToString(digest[:]), Visibility: visibility,
	}
	if err := s.DB.CreateMediaAssetWithVariants(ctx, assetInput, variantInputs); err != nil {
		// DB 写入失败：尽力回滚对象，避免孤儿
		s.rollbackObjects(written)
		return nil, fmt.Errorf("媒体元数据写入失败: %w", err)
	}

	return &database.MediaAsset{
		ID: id, FileName: fileName, OriginalName: assetInput.OriginalName, Mime: mime, Size: int64(len(data)),
		UploaderUserID: in.UploaderUserID, UploaderAdminID: in.UploaderAdminID, Scene: scene, Status: 1,
		StorageProvider: provider, Bucket: s.Bucket, ObjectKey: key, PublicURL: publicURL,
		OwnerType: in.OwnerType, OwnerID: in.OwnerID, GuildUUID: in.GuildUUID,
		Width: width, Height: height, SHA256: assetInput.SHA256, Visibility: visibility,
	}, nil
}

// putObject 按 provider 写入对象字节（S3 / 本地）。
func (s *Service) putObject(ctx context.Context, provider, key string, data []byte, mime string) error {
	if provider == "s3" {
		if err := s.S3.Put(ctx, key, data, mime, cacheControlImmutable); err != nil {
			return fmt.Errorf("S3 保存失败: %w", err)
		}
		return nil
	}
	if err := s.Local.Put(ctx, key, data, mime, cacheControlImmutable); err != nil {
		return fmt.Errorf("本地保存失败: %w", err)
	}
	return nil
}

// rollbackObjects 尽力删除已写入对象；使用独立 5s 超时 ctx，请求 ctx 已取消时也能清理。
func (s *Service) rollbackObjects(keys []string) {
	if len(keys) == 0 {
		return
	}
	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()
	for _, k := range keys {
		if s.S3 != nil {
			_ = s.S3.Delete(ctx, k)
		} else if s.Local != nil {
			_ = s.Local.Delete(ctx, k)
		}
	}
}

// Open 读取媒体字节；媒体不存在时返回 ErrMediaNotFound，其他存储错误原样包装返回。
// S3 对象缺失时回退本地（仅限有 file_name 的旧资产/双写资产）。
func (s *Service) Open(ctx context.Context, a *database.MediaAsset) (io.ReadCloser, string, error) {
	if a == nil {
		return nil, "", ErrMediaNotFound
	}
	mime := a.Mime
	if a.StorageProvider == "s3" && s.S3 != nil && a.ObjectKey != "" {
		obj, err := s.S3.Get(ctx, a.ObjectKey)
		if err == nil {
			if mime == "" {
				mime = obj.ContentType
			}
			return obj.Body, mime, nil
		}
		if !storage.IsNotFound(err) {
			return nil, "", fmt.Errorf("S3 读取失败: %w", err)
		}
	}
	if a.FileName != "" && s.Local != nil {
		obj, err := s.Local.Get(ctx, a.FileName)
		if err == nil {
			return obj.Body, mime, nil
		}
		if !errors.Is(err, fs.ErrNotExist) {
			return nil, "", fmt.Errorf("本地读取失败: %w", err)
		}
	}
	return nil, "", ErrMediaNotFound
}

// OpenVariant 读取变体对象；变体缺失（或未启用 S3）时返回 ErrMediaNotFound。
func (s *Service) OpenVariant(ctx context.Context, v *database.MediaVariant) (io.ReadCloser, string, error) {
	if v == nil || s.S3 == nil || v.ObjectKey == "" {
		return nil, "", ErrMediaNotFound
	}
	obj, err := s.S3.Get(ctx, v.ObjectKey)
	if err != nil {
		if storage.IsNotFound(err) {
			return nil, "", ErrMediaNotFound
		}
		return nil, "", fmt.Errorf("S3 读取变体失败: %w", err)
	}
	mime := v.Mime
	if mime == "" {
		mime = obj.ContentType
	}
	return obj.Body, mime, nil
}

// Delete 删除媒体字节（S3 或本地）。S3 资产会先删除其全部变体对象，避免原图回收后
// @480/@1280 变体成为永久孤儿；变体删除失败只记日志，不影响原图删除（下一轮 GC 会重试）。
func (s *Service) Delete(ctx context.Context, a *database.MediaAsset) error {
	if a == nil {
		return nil
	}
	if a.StorageProvider == "s3" && s.S3 != nil {
		if s.DB != nil {
			variants, err := s.DB.ListMediaVariants(ctx, a.ID)
			if err != nil {
				log.Printf("[MEDIA] 查询变体失败，跳过变体删除 media_id=%s err=%v", a.ID, err)
			}
			for _, v := range variants {
				if v.ObjectKey == "" {
					continue
				}
				if derr := s.S3.Delete(ctx, v.ObjectKey); derr != nil && !storage.IsNotFound(derr) {
					log.Printf("[MEDIA] 删除变体失败 media_id=%s variant=%s key=%s err=%v", a.ID, v.Variant, v.ObjectKey, derr)
				}
			}
		}
		if a.ObjectKey == "" {
			return nil
		}
		return s.S3.Delete(ctx, a.ObjectKey)
	}
	if a.FileName != "" && s.Local != nil {
		return s.Local.Delete(ctx, a.FileName)
	}
	return nil
}

func sniffExt(data []byte) (string, string) {
	switch {
	case len(data) >= 8 && bytes.Equal(data[:8], []byte{0x89, 'P', 'N', 'G', '\r', '\n', 0x1a, '\n'}):
		return ".png", "image/png"
	case len(data) >= 3 && data[0] == 0xFF && data[1] == 0xD8 && data[2] == 0xFF:
		return ".jpg", "image/jpeg"
	case len(data) >= 12 && bytes.Equal(data[:4], []byte("RIFF")) && bytes.Equal(data[8:12], []byte("WEBP")):
		return ".webp", "image/webp"
	case len(data) >= 6 && (string(data[:6]) == "GIF87a" || string(data[:6]) == "GIF89a"):
		return ".gif", "image/gif"
	}
	return "", ""
}

// prepareUpload 在解码信号量保护下完成「解码 + 重编码 + 变体缩放」（并发上限 4）；
// 变体仅 S3 模式生成，且只针对 JPEG/PNG 源图（GIF/WebP 保留原图）。
func (s *Service) prepareUpload(ctx context.Context, data []byte, ext, mime, id, scene, dir string) ([]byte, string, int, int, []variantObject, error) {
	select {
	case decodeSem <- struct{}{}:
		defer func() { <-decodeSem }()
	case <-ctx.Done():
		return nil, "", 0, 0, nil, fmt.Errorf("图片处理已取消")
	}
	img, out, outMime, width, height, err := prepareImage(data, ext, mime)
	if err != nil {
		return nil, "", 0, 0, nil, err
	}
	var variants []variantObject
	if s.S3 != nil && s.VariantsEnabled && (outMime == "image/jpeg" || outMime == "image/png") {
		built, buildErr := buildVariants(img, id, scene, dir)
		if buildErr != nil {
			log.Printf("[MEDIA] 变体生成失败 media_id=%s scene=%s err=%v", id, scene, buildErr)
		} else {
			variants = built
		}
	}
	return out, outMime, width, height, variants, nil
}

// prepareImage 校验像素上限并按 JPEG/PNG 重编码；
// 返回解码后的图像（供变体生成，非 JPEG/PNG 为 nil）。
func prepareImage(data []byte, ext, mime string) (image.Image, []byte, string, int, int, error) {
	cfg, format, err := image.DecodeConfig(bytes.NewReader(data))
	if err != nil {
		return nil, nil, "", 0, 0, fmt.Errorf("图片解码失败")
	}
	if cfg.Width <= 0 || cfg.Height <= 0 || int64(cfg.Width)*int64(cfg.Height) > MaxPixels {
		return nil, nil, "", 0, 0, fmt.Errorf("图片尺寸过大")
	}
	switch format {
	case "jpeg":
		img, _, err := image.Decode(bytes.NewReader(data))
		if err != nil {
			return nil, nil, "", 0, 0, fmt.Errorf("图片解码失败")
		}
		var buf bytes.Buffer
		if err := jpeg.Encode(&buf, img, &jpeg.Options{Quality: 90}); err != nil {
			return nil, nil, "", 0, 0, fmt.Errorf("图片编码失败")
		}
		return img, buf.Bytes(), "image/jpeg", cfg.Width, cfg.Height, nil
	case "png":
		img, _, err := image.Decode(bytes.NewReader(data))
		if err != nil {
			return nil, nil, "", 0, 0, fmt.Errorf("图片解码失败")
		}
		var buf bytes.Buffer
		enc := png.Encoder{CompressionLevel: png.BestSpeed}
		if err := enc.Encode(&buf, img); err != nil {
			return nil, nil, "", 0, 0, fmt.Errorf("图片编码失败")
		}
		if buf.Len() > len(data) {
			return img, data, mime, cfg.Width, cfg.Height, nil
		}
		return img, buf.Bytes(), "image/png", cfg.Width, cfg.Height, nil
	default:
		// GIF（可能动图）与 WebP：保留原始字节，避免破坏动画/透明；不生成变体
		return nil, data, mime, cfg.Width, cfg.Height, nil
	}
}

func truncate(s string, max int) string {
	r := []rune(s)
	if len(r) > max {
		return string(r[:max])
	}
	return s
}
