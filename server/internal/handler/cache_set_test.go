package handler

import "testing"

func TestCacheSetInvalidate(t *testing.T) {
	cs := NewCacheSet()
	cs.Posts.Set("posts:list:1:general", "v")
	cs.Posts.Set("posts:list:2:general", "v")
	cs.PostDetail.Set("post:detail:PS1", "v")

	if !cs.Invalidate("posts", "posts:list:*") {
		t.Fatal("posts scope 应返回 true")
	}
	if _, ok := cs.Posts.Get("posts:list:1:general"); ok {
		t.Fatal("前缀失效后缓存仍存在")
	}
	if !cs.Invalidate("post_detail", "post:detail:PS1") {
		t.Fatal("post_detail scope 应返回 true")
	}
	if _, ok := cs.PostDetail.Get("post:detail:PS1"); ok {
		t.Fatal("精确 key 失效后缓存仍存在")
	}
	if cs.Invalidate("unknown-scope", "x") {
		t.Fatal("未知 scope 应返回 false")
	}
}
