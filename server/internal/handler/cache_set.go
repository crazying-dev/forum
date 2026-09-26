package handler

import (
	"time"

	"yj-forum/server/internal/cache"
)

// CacheSet 各级缓存实例（对齐 legacy cache.py）。
type CacheSet struct {
	Posts      *cache.Cache // 30s / 120s
	PostDetail *cache.Cache // 60s / 300s
	UserInfo   *cache.Cache // 300s / 1800s
	Guilds     *cache.Cache // 30s
	Search     *cache.Cache // 120s / 600s
	Comments   *cache.Cache // 60s / 300s
}

// NewCacheSet 创建默认缓存集。
func NewCacheSet() *CacheSet {
	return &CacheSet{
		Posts:      cache.New(100, 30*time.Second),
		PostDetail: cache.New(200, 60*time.Second),
		UserInfo:   cache.New(200, 300*time.Second),
		Guilds:     cache.New(100, 30*time.Second),
		Search:     cache.New(100, 120*time.Second),
		Comments:   cache.New(200, 60*time.Second),
	}
}

func itoa(n int) string {
	if n == 0 {
		return "0"
	}
	neg := n < 0
	if neg {
		n = -n
	}
	var buf [20]byte
	i := len(buf)
	for n > 0 {
		i--
		buf[i] = byte('0' + n%10)
		n /= 10
	}
	if neg {
		i--
		buf[i] = '-'
	}
	return string(buf[i:])
}
