// Package world 世界频道后台任务：增量消息 poller（广播到 SSE Hub）与每日清理。
package world

import (
	"context"
	"log"
	"strconv"
	"time"

	"yj-forum/server/internal/database"
	"yj-forum/server/internal/sse"
)

// WorldTopic 世界频道 SSE topic（handler 订阅同一 topic）。
const WorldTopic = "world"

const (
	// pollInterval 增量轮询间隔。
	pollInterval = time.Second
	// pollBatch 单次拉取上限（对齐 database.WorldMaxLimit）。
	pollBatch = database.WorldMaxLimit
	// pollOverlap 重叠窗口：重新扫描最近 5 秒已见消息，兜住序列号先分配、后提交的乱序。
	pollOverlap = 5 * time.Second
	// pollOverlapIDs 重叠窗口内最多重扫的 id 数（防止高流量下重复扫描拖慢前进）。
	pollOverlapIDs int64 = 200
	// pollMaxRounds 单轮最多连续拉取批次数（积压时快速追平）。
	pollMaxRounds = 10

	// cleanupHour 每日清理时刻（Asia/Shanghai）。
	cleanupHour = 3
)

// messageSource 便于 poller 单测注入假数据源。
type messageSource interface {
	ListWorldMessages(ctx context.Context, beforeID, afterID int64, limit int) ([]database.WorldMessage, bool, error)
	ListWorldAfterID(ctx context.Context, id int64, limit int) ([]database.WorldMessage, error)
}

type poller struct {
	src    messageSource
	hub    *sse.Hub
	lastID int64
	ready  bool
	// seen 最近广播过的消息 id -> 首次广播时间，用于 5 秒重叠窗口去重。
	seen map[int64]time.Time
}

// StartPoller 启动世界频道增量轮询（每 1 秒），新消息广播到 topic world。
// 启动时先对齐当前最大 id（历史消息由 SSE 首包负责），之后只推送新消息。
func StartPoller(ctx context.Context, db *database.DB, hub *sse.Hub) {
	if db == nil || hub == nil {
		return
	}
	p := &poller{src: db, hub: hub, seen: make(map[int64]time.Time, 1024)}
	go p.run(ctx)
}

func (p *poller) run(ctx context.Context) {
	if err := p.init(ctx); err != nil {
		log.Printf("[WORLD] poller 初始化失败（稍后重试）: %v", err)
	}
	ticker := time.NewTicker(pollInterval)
	defer ticker.Stop()
	for {
		select {
		case <-ctx.Done():
			return
		case now := <-ticker.C:
			if !p.ready {
				if err := p.init(ctx); err != nil {
					log.Printf("[WORLD] poller 初始化重试失败: %v", err)
					continue
				}
			}
			p.pollOnce(ctx, now)
		}
	}
}

// init 记录启动时的最新消息 id，并把最近一页历史标记为已见，
// 避免把历史消息当作新消息广播（重叠窗口重扫时也不会重复推送）。
func (p *poller) init(ctx context.Context) error {
	items, _, err := p.src.ListWorldMessages(ctx, 0, 0, pollBatch)
	if err != nil {
		return err
	}
	now := time.Now()
	for _, m := range items {
		p.seen[m.ID] = now
	}
	if len(items) > 0 {
		p.lastID = items[0].ID
	}
	p.ready = true
	return nil
}

// pollOnce 一轮轮询：先向前抓新消息，再在 5 秒重叠窗口内重扫一遍去重。
func (p *poller) pollOnce(ctx context.Context, now time.Time) {
	p.pollForward(ctx, now)
	p.pollOverlap(ctx, now)
	p.pruneSeen(now.Add(-pollOverlap))
}

// pollForward 从 lastID 之后按 id 升序拉取；一次拿满则继续，最多 pollMaxRounds 批。
func (p *poller) pollForward(ctx context.Context, now time.Time) {
	from := p.lastID
	for round := 0; round < pollMaxRounds; round++ {
		msgs, err := p.src.ListWorldAfterID(ctx, from, pollBatch)
		if err != nil {
			log.Printf("[WORLD] poller 查询失败: %v", err)
			return
		}
		p.broadcastNew(msgs, now)
		if len(msgs) < pollBatch {
			return
		}
		from = p.lastID
	}
}

// pollOverlap 在最近 5 秒内有广播时重扫 lastID 之前的窗口，补偿「id 小但提交晚」的消息。
// 重扫范围限制在最近 pollOverlapIDs 个 id 内，避免高流量下反复扫旧数据。
func (p *poller) pollOverlap(ctx context.Context, now time.Time) {
	if p.lastID <= 0 {
		return
	}
	// 仅当重叠窗口内仍有广播记录时重扫；长时间无消息则无晚提交可补。
	if !p.hasSeenSince(now.Add(-pollOverlap)) {
		return
	}
	from := p.lastID - pollOverlapIDs
	if from < 0 {
		from = 0
	}
	msgs, err := p.src.ListWorldAfterID(ctx, from, pollBatch)
	if err != nil {
		log.Printf("[WORLD] poller 重叠窗口查询失败: %v", err)
		return
	}
	p.broadcastNew(msgs, now)
}

// broadcastNew 广播未见过的新消息（seen 去重），返回广播条数。
func (p *poller) broadcastNew(msgs []database.WorldMessage, now time.Time) int {
	n := 0
	for _, m := range msgs {
		if _, seen := p.seen[m.ID]; seen {
			continue
		}
		p.seen[m.ID] = now
		if m.ID > p.lastID {
			p.lastID = m.ID
		}
		p.hub.Broadcast(WorldTopic, sse.Event{
			ID:   strconv.FormatInt(m.ID, 10),
			Type: "message",
			Data: m,
		})
		n++
	}
	return n
}

// hasSeenSince 返回 cutoff 之后是否有广播记录（用于判断重叠窗口是否活跃）。
func (p *poller) hasSeenSince(cutoff time.Time) bool {
	for _, at := range p.seen {
		if !at.Before(cutoff) {
			return true
		}
	}
	return false
}

// pruneSeen 清理超过重叠窗口的去重记录。
func (p *poller) pruneSeen(cutoff time.Time) {
	for id, at := range p.seen {
		if at.Before(cutoff) {
			delete(p.seen, id)
		}
	}
}

// StartCleanup 启动每日清理任务：每天 Asia/Shanghai 03:00 保留最新 10000 条。
func StartCleanup(ctx context.Context, db *database.DB) {
	if db == nil {
		return
	}
	go runCleanup(ctx, db)
}

func runCleanup(ctx context.Context, db *database.DB) {
	loc := shanghaiLocation()
	for {
		now := time.Now().In(loc)
		timer := time.NewTimer(time.Until(nextCleanupTime(now, loc)))
		select {
		case <-ctx.Done():
			timer.Stop()
			return
		case <-timer.C:
			deleted, err := db.WorldCleanup(ctx)
			if err != nil {
				log.Printf("[WORLD] 清理失败: %v", err)
				continue
			}
			if deleted > 0 {
				log.Printf("[WORLD] 已清理 %d 条历史消息（保留最新 %d 条）", deleted, database.WorldKeepCount)
			}
		}
	}
}

// nextCleanupTime 返回 now 之后的下一个 03:00（loc 时区）；恰好 03:00 时取次日。
func nextCleanupTime(now time.Time, loc *time.Location) time.Time {
	local := now.In(loc)
	next := time.Date(local.Year(), local.Month(), local.Day(), cleanupHour, 0, 0, 0, loc)
	if !next.After(local) {
		next = next.AddDate(0, 0, 1)
	}
	return next
}

// shanghaiLocation Asia/Shanghai；无 tzdata 环境回退到固定 +08:00。
func shanghaiLocation() *time.Location {
	if loc, err := time.LoadLocation("Asia/Shanghai"); err == nil {
		return loc
	}
	return time.FixedZone("CST", 8*60*60)
}
