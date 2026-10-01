// Package cache 实现进程内 LRU + TTL 缓存（对齐 legacy api/cache.py 的 L1）。
package cache

import (
	"container/list"
	"sync"
	"time"
)

// entry 缓存项。
type entry struct {
	key      string
	value    any
	expireAt time.Time
}

// Cache 线程安全 LRU + TTL。
type Cache struct {
	mu       sync.Mutex
	capacity int
	ttl      time.Duration
	items    map[string]*list.Element
	lru      *list.List
}

// New 创建缓存。
func New(capacity int, ttl time.Duration) *Cache {
	if capacity < 1 {
		capacity = 100
	}
	return &Cache{
		capacity: capacity,
		ttl:      ttl,
		items:    make(map[string]*list.Element),
		lru:      list.New(),
	}
}

// Get 读取；过期自动删除。
func (c *Cache) Get(key string) (any, bool) {
	c.mu.Lock()
	defer c.mu.Unlock()
	elem, ok := c.items[key]
	if !ok {
		return nil, false
	}
	ent := elem.Value.(*entry)
	if c.ttl > 0 && time.Now().After(ent.expireAt) {
		c.lru.Remove(elem)
		delete(c.items, key)
		return nil, false
	}
	c.lru.MoveToFront(elem)
	return ent.value, true
}

// Set 写入。
func (c *Cache) Set(key string, value any, ttl ...time.Duration) {
	t := c.ttl
	if len(ttl) > 0 && ttl[0] > 0 {
		t = ttl[0]
	}
	c.mu.Lock()
	defer c.mu.Unlock()
	if elem, ok := c.items[key]; ok {
		ent := elem.Value.(*entry)
		ent.value = value
		ent.expireAt = time.Now().Add(t)
		c.lru.MoveToFront(elem)
		return
	}
	ent := &entry{key: key, value: value, expireAt: time.Now().Add(t)}
	elem := c.lru.PushFront(ent)
	c.items[key] = elem
	for c.lru.Len() > c.capacity {
		last := c.lru.Back()
		if last == nil {
			break
		}
		c.lru.Remove(last)
		delete(c.items, last.Value.(*entry).key)
	}
}

// SetIfAbsent 原子占位：仅当键不存在（或已过期）时写入并返回 true；已存在则返回 false。
// 用于去重等「先占位再执行」场景（Get+Set 组合在并发下不原子）。
func (c *Cache) SetIfAbsent(key string, value any, ttl ...time.Duration) bool {
	c.mu.Lock()
	defer c.mu.Unlock()
	if elem, ok := c.items[key]; ok {
		ent := elem.Value.(*entry)
		if c.ttl > 0 && time.Now().After(ent.expireAt) {
			// 已过期：删除后按新项写入
			c.lru.Remove(elem)
			delete(c.items, key)
		} else {
			c.lru.MoveToFront(elem)
			return false
		}
	}
	t := c.ttl
	if len(ttl) > 0 && ttl[0] > 0 {
		t = ttl[0]
	}
	ent := &entry{key: key, value: value, expireAt: time.Now().Add(t)}
	c.items[key] = c.lru.PushFront(ent)
	for c.lru.Len() > c.capacity {
		last := c.lru.Back()
		if last == nil {
			break
		}
		c.lru.Remove(last)
		delete(c.items, last.Value.(*entry).key)
	}
	return true
}

// Delete 删除。
func (c *Cache) Delete(key string) {
	c.mu.Lock()
	defer c.mu.Unlock()
	if elem, ok := c.items[key]; ok {
		c.lru.Remove(elem)
		delete(c.items, key)
	}
}

// DeletePrefix 按前缀删除（缓存失效）。
func (c *Cache) DeletePrefix(prefix string) {
	c.mu.Lock()
	defer c.mu.Unlock()
	for k, elem := range c.items {
		if len(k) >= len(prefix) && k[:len(prefix)] == prefix {
			c.lru.Remove(elem)
			delete(c.items, k)
		}
	}
}

// Clear 清空。
func (c *Cache) Clear() {
	c.mu.Lock()
	defer c.mu.Unlock()
	c.items = make(map[string]*list.Element)
	c.lru.Init()
}

// Len 数量。
func (c *Cache) Len() int {
	c.mu.Lock()
	defer c.mu.Unlock()
	return c.lru.Len()
}
