package world

import (
	"context"
	"sync"
	"testing"
	"time"

	"yj-forum/server/internal/database"
	"yj-forum/server/internal/sse"
)

// fakeWorldSource 内存版消息源（按 id 升序存储）。
type fakeWorldSource struct {
	mu   sync.Mutex
	msgs []database.WorldMessage
}

func (f *fakeWorldSource) ListWorldMessages(_ context.Context, _, _ int64, limit int) ([]database.WorldMessage, bool, error) {
	f.mu.Lock()
	defer f.mu.Unlock()
	limit = database.NormalizeWorldLimit(limit)
	items := []database.WorldMessage{}
	for i := len(f.msgs) - 1; i >= 0 && len(items) < limit+1; i-- {
		items = append(items, f.msgs[i])
	}
	hasMore := len(items) > limit
	if hasMore {
		items = items[:limit]
	}
	return items, hasMore, nil
}

func (f *fakeWorldSource) ListWorldAfterID(_ context.Context, id int64, limit int) ([]database.WorldMessage, error) {
	f.mu.Lock()
	defer f.mu.Unlock()
	limit = database.NormalizeWorldLimit(limit)
	items := []database.WorldMessage{}
	for _, m := range f.msgs {
		if m.ID > id {
			items = append(items, m)
			if len(items) >= limit {
				break
			}
		}
	}
	return items, nil
}

func (f *fakeWorldSource) add(ids ...int64) {
	f.mu.Lock()
	defer f.mu.Unlock()
	for _, id := range ids {
		f.msgs = append(f.msgs, database.WorldMessage{ID: id, Content: "m"})
	}
}

func newTestPoller(src messageSource) (*poller, *sse.Hub, *sse.Client) {
	hub := sse.NewHub()
	client := hub.Subscribe(WorldTopic, 4096)
	return &poller{src: src, hub: hub, seen: map[int64]time.Time{}}, hub, client
}

func drainWorldEvents(ch <-chan sse.Event) []sse.Event {
	evts := []sse.Event{}
	for {
		select {
		case ev := <-ch:
			evts = append(evts, ev)
		default:
			return evts
		}
	}
}

func TestPollerInitSkipsHistoryAndPushesNew(t *testing.T) {
	src := &fakeWorldSource{}
	src.add(1, 2, 3)
	p, _, client := newTestPoller(src)
	defer p.hub.Unsubscribe(WorldTopic, client)
	base := time.Now()

	if err := p.init(context.Background()); err != nil {
		t.Fatalf("init: %v", err)
	}
	if p.lastID != 3 {
		t.Fatalf("init lastID = %d, want 3", p.lastID)
	}
	if evts := drainWorldEvents(client.Ch); len(evts) != 0 {
		t.Fatalf("初始化不应广播历史消息，got %d", len(evts))
	}

	src.add(4, 5)
	p.pollOnce(context.Background(), base.Add(time.Second))
	evts := drainWorldEvents(client.Ch)
	if len(evts) != 2 {
		t.Fatalf("新消息广播 %d 条, want 2", len(evts))
	}
	if evts[0].ID != "4" || evts[1].ID != "5" {
		t.Fatalf("广播顺序 = [%s,%s], want [4,5]", evts[0].ID, evts[1].ID)
	}
	if evts[0].Type != "message" {
		t.Fatalf("事件类型 = %q, want message", evts[0].Type)
	}

	// 重叠窗口重扫同一批消息：seen 去重，不应重复广播。
	p.pollOnce(context.Background(), base.Add(2*time.Second))
	if evts := drainWorldEvents(client.Ch); len(evts) != 0 {
		t.Fatalf("重复轮询不应广播，got %d", len(evts))
	}
}

func TestPollerOverlapCatchesLateCommit(t *testing.T) {
	src := &fakeWorldSource{}
	src.add(1, 2, 3)
	p, _, client := newTestPoller(src)
	defer p.hub.Unsubscribe(WorldTopic, client)
	base := time.Now()
	if err := p.init(context.Background()); err != nil {
		t.Fatalf("init: %v", err)
	}

	// id=5 先提交并被广播，id=4 后提交（序列号小、提交晚）。
	src.add(5)
	p.pollOnce(context.Background(), base.Add(time.Second))
	if evts := drainWorldEvents(client.Ch); len(evts) != 1 || evts[0].ID != "5" {
		t.Fatalf("首批广播 = %v, want [5]", evts)
	}

	src.add(4)
	p.pollOnce(context.Background(), base.Add(2*time.Second))
	evts := drainWorldEvents(client.Ch)
	if len(evts) != 1 || evts[0].ID != "4" {
		t.Fatalf("重叠窗口应补发晚提交的 id=4，got %v", evts)
	}
}

func TestPollerCatchesUpInBatches(t *testing.T) {
	src := &fakeWorldSource{}
	p, _, client := newTestPoller(src)
	defer p.hub.Unsubscribe(WorldTopic, client)
	base := time.Now()
	if err := p.init(context.Background()); err != nil {
		t.Fatalf("init: %v", err)
	}

	// 一次积压 600 条：poller 应分两批（500 + 100）追平。
	ids := make([]int64, 0, 600)
	for i := int64(1); i <= 600; i++ {
		ids = append(ids, i)
	}
	src.add(ids...)
	p.pollOnce(context.Background(), base.Add(time.Second))
	if got := len(drainWorldEvents(client.Ch)); got != 600 {
		t.Fatalf("追平广播 %d 条, want 600", got)
	}
	if p.lastID != 600 {
		t.Fatalf("lastID = %d, want 600", p.lastID)
	}
}

func TestNextCleanupTime(t *testing.T) {
	loc := time.FixedZone("CST", 8*60*60)
	cases := []struct {
		name string
		now  time.Time
		want time.Time
	}{
		{
			name: "凌晨等待当日 03:00",
			now:  time.Date(2026, 10, 18, 2, 0, 0, 0, loc),
			want: time.Date(2026, 10, 18, 3, 0, 0, 0, loc),
		},
		{
			name: "白天取次日 03:00",
			now:  time.Date(2026, 10, 18, 4, 0, 0, 0, loc),
			want: time.Date(2026, 10, 19, 3, 0, 0, 0, loc),
		},
		{
			name: "恰好 03:00 取次日",
			now:  time.Date(2026, 10, 18, 3, 0, 0, 0, loc),
			want: time.Date(2026, 10, 19, 3, 0, 0, 0, loc),
		},
		{
			name: "跨月",
			now:  time.Date(2026, 10, 31, 23, 30, 0, 0, loc),
			want: time.Date(2026, 11, 1, 3, 0, 0, 0, loc),
		},
		{
			name: "UTC 输入按上海时区计算",
			now:  time.Date(2026, 10, 17, 18, 30, 0, 0, time.UTC), // = 10-18 02:30 CST
			want: time.Date(2026, 10, 18, 3, 0, 0, 0, loc),
		},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			got := nextCleanupTime(tc.now, loc)
			if !got.Equal(tc.want) {
				t.Fatalf("nextCleanupTime = %s, want %s", got, tc.want)
			}
		})
	}
}

func TestShanghaiLocation(t *testing.T) {
	loc := shanghaiLocation()
	_, offset := time.Date(2026, 10, 18, 3, 0, 0, 0, loc).Zone()
	if offset != 8*60*60 {
		t.Fatalf("上海时区偏移 = %d, want 28800", offset)
	}
}
