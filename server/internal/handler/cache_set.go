package handler

import (
	"strings"
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
	ViewDedup  *cache.Cache // 浏览去重 30min
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
		ViewDedup:  cache.New(10000, 30*time.Minute),
	}
}

// Invalidate 应用 cache_invalidations 消费者投递的失效指令。
// scope 标识缓存域，key 支持 "*" 后缀（按前缀删除）；返回 false 表示 scope 未知。
func (s *CacheSet) Invalidate(scope, key string) bool {
	if s == nil {
		return false
	}
	var c *cache.Cache
	switch strings.ToLower(strings.TrimSpace(scope)) {
	case "posts", "post_list", "post:list":
		c = s.Posts
	case "post_detail", "post", "post:detail":
		c = s.PostDetail
	case "comments", "comment":
		c = s.Comments
	case "users", "user", "user_info", "user:info":
		c = s.UserInfo
	case "guilds", "guild":
		c = s.Guilds
	case "search":
		c = s.Search
	case "view_dedup", "view:dedup":
		c = s.ViewDedup
	case "site_config", "announcement", "blacklist", "changelog":
		// 这些配置/日志直接读 PG，没有进程内缓存；消费成功即可，避免队列重试至死信
		return true
	default:
		return false
	}
	key = strings.TrimSpace(key)
	if strings.HasSuffix(key, "*") {
		c.DeletePrefix(strings.TrimSuffix(key, "*"))
	} else {
		c.Delete(key)
	}
	return true
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
