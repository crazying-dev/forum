// Package media 统一媒体保存/读取（SeaweedFS S3 / 旧本地目录）。
package media

import (
	"bytes"
	"context"
	"crypto/sha256"
	"encoding/hex"
	"fmt"
	"image"
	"image/jpeg"
	"image/png"
	"io"
	"strings"
	"time"

	_ "golang.org/x/image/webp"
	_ "image/gif" // 注册 gif 解码

	"yj-forum/server/internal/database"
	"yj-forum/server/internal/storage"
)

const (
	MaxInputBytes = 5 << 20
	MaxPixels     = 50_000_000
)

// Service 媒体服务。
type Service struct {
	DB     *database.DB
	S3     *storage.S3Provider
	Local  *storage.LocalProvider
	Bucket string
}

// NewService 创建媒体服务；s3 为 nil 时回退本地目录。
func NewService(db *database.DB, s3 *storage.S3Provider, localDir, bucket string) *Service {
	return &Service{DB: db, S3: s3, Local: &storage.LocalProvider{Dir: localDir}, Bucket: bucket}
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
	data, mime, width, height, err := prepareImage(in.Data, ext, mime)
	if err != nil {
		return nil, err
	}
	if int64(len(data)) > maxBytes {
		return nil, fmt.Errorf("图片处理后超过大小上限")
	}

	id, err := database.GenMediaID()
	if err != nil {
		return nil, err
	}
	digest := sha256.Sum256(data)
	scene := strings.Trim(strings.TrimSpace(in.Scene), "/")
	if scene == "" {
		scene = "misc"
	}
	provider, key, fileName := "local", id+ext, id+ext
	publicURL := "/ov2/api/media/" + id

	if s.S3 != nil {
		provider = "s3"
		key = scene + "/" + time.Now().Format("2006/01") + "/" + id + ext
		fileName = ""
		if err := s.S3.Put(ctx, key, data, mime, "public, max-age=31536000, immutable"); err != nil {
			return nil, fmt.Errorf("S3 保存失败: %w", err)
		}
	} else {
		if err := s.Local.Put(ctx, key, data, mime, "public, max-age=31536000, immutable"); err != nil {
			return nil, fmt.Errorf("本地保存失败: %w", err)
		}
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
	if err := s.DB.CreateMediaAsset(ctx, assetInput); err != nil {
		// DB 写入失败：尽力回滚对象，避免孤儿
		if s.S3 != nil {
			_ = s.S3.Delete(ctx, key)
		} else {
			_ = s.Local.Delete(ctx, key)
		}
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

// Open 读取媒体字节；S3 失败时回退本地（仅限有 file_name 的旧资产/双写资产）。
func (s *Service) Open(ctx context.Context, a *database.MediaAsset) (io.ReadCloser, string, error) {
	if a == nil {
		return nil, "", fmt.Errorf("媒体不存在")
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
	}
	if a.FileName != "" && s.Local != nil {
		obj, err := s.Local.Get(ctx, a.FileName)
		if err == nil {
			return obj.Body, mime, nil
		}
	}
	return nil, "", fmt.Errorf("媒体不存在")
}

// Delete 删除媒体字节（S3 或本地）。
func (s *Service) Delete(ctx context.Context, a *database.MediaAsset) error {
	if a == nil {
		return nil
	}
	if a.StorageProvider == "s3" && s.S3 != nil && a.ObjectKey != "" {
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

func prepareImage(data []byte, ext, mime string) ([]byte, string, int, int, error) {
	cfg, format, err := image.DecodeConfig(bytes.NewReader(data))
	if err != nil {
		return nil, "", 0, 0, fmt.Errorf("图片解码失败")
	}
	if cfg.Width <= 0 || cfg.Height <= 0 || int64(cfg.Width)*int64(cfg.Height) > MaxPixels {
		return nil, "", 0, 0, fmt.Errorf("图片尺寸过大")
	}
	switch format {
	case "jpeg":
		img, _, err := image.Decode(bytes.NewReader(data))
		if err != nil {
			return nil, "", 0, 0, fmt.Errorf("图片解码失败")
		}
		var buf bytes.Buffer
		if err := jpeg.Encode(&buf, img, &jpeg.Options{Quality: 90}); err != nil {
			return nil, "", 0, 0, fmt.Errorf("图片编码失败")
		}
		return buf.Bytes(), "image/jpeg", cfg.Width, cfg.Height, nil
	case "png":
		img, _, err := image.Decode(bytes.NewReader(data))
		if err != nil {
			return nil, "", 0, 0, fmt.Errorf("图片解码失败")
		}
		var buf bytes.Buffer
		enc := png.Encoder{CompressionLevel: png.BestSpeed}
		if err := enc.Encode(&buf, img); err != nil {
			return nil, "", 0, 0, fmt.Errorf("图片编码失败")
		}
		if buf.Len() > len(data) {
			return data, mime, cfg.Width, cfg.Height, nil
		}
		return buf.Bytes(), "image/png", cfg.Width, cfg.Height, nil
	default:
		// GIF（可能动图）与 WebP：保留原始字节，避免破坏动画/透明
		return data, mime, cfg.Width, cfg.Height, nil
	}
}

func truncate(s string, max int) string {
	r := []rune(s)
	if len(r) > max {
		return string(r[:max])
	}
	return s
}
