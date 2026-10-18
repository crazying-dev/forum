package database

import (
	"testing"
	"time"
)

func TestNormalizeWorldLimit(t *testing.T) {
	cases := []struct {
		name string
		in   int
		want int
	}{
		{"零值回落默认", 0, WorldDefaultLimit},
		{"负数回落默认", -10, WorldDefaultLimit},
		{"正常值", 50, 50},
		{"上限内", 500, 500},
		{"500 上限截断", 501, WorldMaxLimit},
		{"超大值截断", 10000, WorldMaxLimit},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			if got := NormalizeWorldLimit(tc.in); got != tc.want {
				t.Fatalf("NormalizeWorldLimit(%d) = %d, want %d", tc.in, got, tc.want)
			}
		})
	}
}

func TestNormalizeWorldCursors(t *testing.T) {
	cases := []struct {
		name                  string
		before, after         int64
		wantBefore, wantAfter int64
	}{
		{"都未提供", 0, 0, 0, 0},
		{"负数视为未提供", -1, -2, 0, 0},
		{"仅 before", 100, 0, 100, 0},
		{"仅 after", 0, 200, 0, 200},
		{"同时提供 after 优先", 100, 200, 0, 200},
		{"before 负 after 正", -5, 200, 0, 200},
		{"before 正 after 负", 100, -5, 100, 0},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			before, after := NormalizeWorldCursors(tc.before, tc.after)
			if before != tc.wantBefore || after != tc.wantAfter {
				t.Fatalf("NormalizeWorldCursors(%d,%d) = (%d,%d), want (%d,%d)",
					tc.before, tc.after, before, after, tc.wantBefore, tc.wantAfter)
			}
		})
	}
}

func TestWorldSendAllowed(t *testing.T) {
	now := time.Date(2026, 10, 18, 12, 0, 0, 0, time.UTC)
	at := func(d time.Duration) *time.Time {
		t := now.Add(d)
		return &t
	}
	zero := time.Time{}
	cases := []struct {
		name string
		last *time.Time
		want bool
	}{
		{"从未发言", nil, true},
		{"零值时间", &zero, true},
		{"1.999 秒内限流", at(-1999 * time.Millisecond), false},
		{"刚好 2 秒放行", at(-2 * time.Second), true},
		{"超过 2 秒放行", at(-10 * time.Second), true},
		{"未来时间（时钟回拨）限流", at(time.Second), false},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			if got := worldSendAllowed(tc.last, now); got != tc.want {
				t.Fatalf("worldSendAllowed(%v) = %v, want %v", tc.last, got, tc.want)
			}
		})
	}
}

func TestWorldCleanupCutoffOffset(t *testing.T) {
	cases := []struct {
		name       string
		total      int64
		keep       int64
		wantOffset int64
		wantNeed   bool
	}{
		{"空表", 0, WorldKeepCount, 0, false},
		{"不足保留数", 9999, WorldKeepCount, 0, false},
		{"恰好保留数", 10000, WorldKeepCount, 0, false},
		{"多一条", 10001, WorldKeepCount, 10000, true},
		{"大量历史", 25000, WorldKeepCount, 10000, true},
		{"keep 非正防御", 1, 0, 0, false},
		{"keep 非正防御-两条", 2, 0, 1, true},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			offset, need := worldCleanupCutoffOffset(tc.total, tc.keep)
			if offset != tc.wantOffset || need != tc.wantNeed {
				t.Fatalf("worldCleanupCutoffOffset(%d,%d) = (%d,%v), want (%d,%v)",
					tc.total, tc.keep, offset, need, tc.wantOffset, tc.wantNeed)
			}
		})
	}
}

// TestWorldCleanupCutoffKeepsNewest 用降序 id 模型验证 cutoff 选择：
// total=25000、keep=10000 时 cutoff 为 id 15000，删除 id<=15000 后恰好剩 10000 条。
func TestWorldCleanupCutoffKeepsNewest(t *testing.T) {
	const total = int64(25000)
	offset, need := worldCleanupCutoffOffset(total, WorldKeepCount)
	if !need {
		t.Fatal("25000 > 10000 时应触发清理")
	}
	// 降序第一行 id=total，OFFSET offset 对应 id=total-offset。
	cutoffID := total - offset
	if cutoffID != 15000 {
		t.Fatalf("cutoff id = %d, want 15000", cutoffID)
	}
	remaining := total - cutoffID
	if remaining != WorldKeepCount {
		t.Fatalf("删除 id<=cutoff 后剩余 %d 条，want %d", remaining, WorldKeepCount)
	}
}

func TestWorldCleanupBatchSizeRange(t *testing.T) {
	if worldCleanupBatchSize < 500 || worldCleanupBatchSize > 2000 {
		t.Fatalf("清理批大小 %d 超出契约范围 500-2000", worldCleanupBatchSize)
	}
}
