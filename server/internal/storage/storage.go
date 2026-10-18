// Package storage 抽象媒体字节存储（SeaweedFS S3 / 旧本地目录）。
package storage

import (
	"context"
	"io"
)

// Object 读取结果。
type Object struct {
	Body        io.ReadCloser
	ContentType string
	Size        int64
}

// Provider 媒体存储提供者。
type Provider interface {
	Put(ctx context.Context, key string, data []byte, contentType, cacheControl string) error
	Get(ctx context.Context, key string) (*Object, error)
	Delete(ctx context.Context, key string) error
	Exists(ctx context.Context, key string) (bool, error)
}
