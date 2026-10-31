package legacy

import (
	"errors"
	"sync/atomic"
	"testing"
	"time"
)

func TestCompareVersions(t *testing.T) {
	cases := []struct {
		a, b string
		want int
	}{
		{"1.3.18", "1.3.18", 0},
		{"1.3.17", "1.3.18", -1},
		{"1.4", "1.3.18", 1},
		{"Windows-V1.3.18", "1.3.18", 0},
		{"2.0", "2.0.0", 0},
		{"", "0.0.0", 0},
	}
	for _, tc := range cases {
		if got := CompareVersions(tc.a, tc.b); got != tc.want {
			t.Errorf("CompareVersions(%q,%q)=%d，期望 %d", tc.a, tc.b, got, tc.want)
		}
	}
}

// testManifest 构造测试用发布清单（不再依赖已删除的内置兜底清单）。
func testManifest() *ReleaseManifest {
	return &ReleaseManifest{
		Schema:      1,
		MinVersions: map[string]string{"windows": "1.3.18", "web": "0"},
		Platforms: []ReleasePlatform{
			{Key: "windows", Name: "Windows", Status: "available", Releases: []ReleaseAsset{
				{Version: "1.3.18", Channel: "stable", Filename: "forum_setup.exe", URL: "https://example.com/forum_setup.exe"},
			}},
		},
	}
}

func TestCheckRelease(t *testing.T) {
	m := testManifest()
	payload := CheckRelease(m, "windows", "1.0.0")
	if payload == nil {
		t.Fatal("windows 应存在")
	}
	if payload["min_version"] != "1.3.18" || payload["too_low"] != true {
		t.Fatalf("min_version/too_low 不符：%v", payload)
	}
	if payload["latest"] != "1.3.18" || payload["available"] != true {
		t.Fatalf("latest/available 不符：%v", payload)
	}
	if CheckRelease(m, "nope", "1.0.0") != nil {
		t.Fatal("未知平台应返回 nil")
	}
}

// 未预热时 CachedManifest 返回空清单且不触发网络。
func TestReleaseProviderColdCacheEmpty(t *testing.T) {
	provider := NewReleaseProvider("")
	var fetchCalls int32
	provider.Fetch = func() (*ReleaseManifest, error) {
		atomic.AddInt32(&fetchCalls, 1)
		return nil, errors.New("github 不可达")
	}

	m := provider.CachedManifest()
	if m == nil {
		t.Fatal("未预热时 CachedManifest 不应返回 nil")
	}
	if len(m.Platforms) != 0 || len(m.MinVersions) != 0 {
		t.Fatalf("未预热应返回空清单：platforms=%d min_versions=%d", len(m.Platforms), len(m.MinVersions))
	}
	if got := atomic.LoadInt32(&fetchCalls); got != 0 {
		t.Fatalf("CachedManifest 不应触发网络，实际 Fetch %d 次", got)
	}
	// 未预热时 MinVersion 不拦截（异步拉取失败后仍是空串）。
	if got := provider.MinVersion("windows"); got != "" {
		t.Fatalf("未预热时 MinVersion(windows)=%q，期望空串", got)
	}
}

// GitHub 拉取失败时返回空清单：无平台、无 min_versions，MinVersion 为空串。
func TestReleaseProviderEmptyManifestOnFetchError(t *testing.T) {
	provider := NewReleaseProvider("")
	provider.Fetch = func() (*ReleaseManifest, error) {
		return nil, errors.New("github 不可达")
	}

	m := provider.Manifest()
	if m == nil {
		t.Fatal("Manifest 不应返回 nil")
	}
	if m.Schema != 1 || len(m.Platforms) != 0 || len(m.MinVersions) != 0 {
		t.Fatalf("拉取失败应返回空清单：%+v", m)
	}
	if hasAnyRelease(m) {
		t.Fatal("空清单不应有任何 release")
	}
	if got := provider.MinVersion("windows"); got != "" {
		t.Fatalf("拉取失败时 MinVersion(windows)=%q，期望空串", got)
	}
	if got := provider.MinVersion("android"); got != "" {
		t.Fatalf("拉取失败时 MinVersion(android)=%q，期望空串", got)
	}
}

// 拉取失败时保留上一份成功清单（stale-while-error），不清空已可用的发布信息。
func TestReleaseProviderKeepsLastGoodManifestOnFetchError(t *testing.T) {
	provider := NewReleaseProvider("")
	provider.TTL = time.Millisecond
	var fail int32
	provider.Fetch = func() (*ReleaseManifest, error) {
		if atomic.LoadInt32(&fail) == 1 {
			return nil, errors.New("github 不可达")
		}
		return testManifest(), nil
	}
	if m := provider.Manifest(); !hasAnyRelease(m) {
		t.Fatal("首次拉取应有发布数据")
	}
	atomic.StoreInt32(&fail, 1)
	time.Sleep(5 * time.Millisecond)
	m := provider.Manifest()
	if !hasAnyRelease(m) {
		t.Fatalf("拉取失败后应保留上一份清单：%+v", m)
	}
	if got := provider.MinVersion("windows"); got != "1.3.18" {
		t.Fatalf("拉取失败后 MinVersion(windows)=%q，期望 1.3.18", got)
	}
}

func TestParseSince(t *testing.T) {
	valid := []string{"2026-05-06", "2026-05-06 12:00:00", "2026-05-06T12:00:00.123456Z", "2026-05-06 12:00:00+08:00"}
	for _, v := range valid {
		if ParseSince(v) != v {
			t.Errorf("%q 应接受", v)
		}
	}
	for _, v := range []string{"", "not-a-time", "2026-13-40 99:99:99", "2026-05-06; drop table users"} {
		if ParseSince(v) != "" {
			t.Errorf("%q 应忽略", v)
		}
	}
}
