package storage

import (
	"context"
	"fmt"
	"os"
	"path/filepath"
	"strings"
)

// LocalProvider 旧本地目录提供者（file_name 语义，不含子目录）。
type LocalProvider struct {
	Dir string
}

func (p *LocalProvider) safePath(key string) (string, error) {
	if key == "" || strings.Contains(key, "..") || strings.Contains(key, "/") || strings.Contains(key, "\\") {
		return "", fmt.Errorf("非法文件名")
	}
	return filepath.Join(p.Dir, key), nil
}

func (p *LocalProvider) Put(ctx context.Context, key string, data []byte, contentType, cacheControl string) error {
	full, err := p.safePath(key)
	if err != nil {
		return err
	}
	if err := os.MkdirAll(p.Dir, 0755); err != nil {
		return err
	}
	return os.WriteFile(full, data, 0644)
}

func (p *LocalProvider) Get(ctx context.Context, key string) (*Object, error) {
	full, err := p.safePath(key)
	if err != nil {
		return nil, err
	}
	f, err := os.Open(full)
	if err != nil {
		return nil, err
	}
	st, err := f.Stat()
	if err != nil {
		_ = f.Close()
		return nil, err
	}
	return &Object{Body: f, Size: st.Size()}, nil
}

func (p *LocalProvider) Delete(ctx context.Context, key string) error {
	full, err := p.safePath(key)
	if err != nil {
		return err
	}
	err = os.Remove(full)
	if os.IsNotExist(err) {
		return nil
	}
	return err
}

func (p *LocalProvider) Exists(ctx context.Context, key string) (bool, error) {
	full, err := p.safePath(key)
	if err != nil {
		return false, err
	}
	_, err = os.Stat(full)
	if os.IsNotExist(err) {
		return false, nil
	}
	return err == nil, err
}
