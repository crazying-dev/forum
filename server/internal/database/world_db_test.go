package database

import (
	"context"
	"errors"
	"fmt"
	"testing"
)

// resetWorldMessages 清空世界频道（测试库独立 schema；用例串行执行）。
func resetWorldMessages(t *testing.T, db *DB) {
	t.Helper()
	ctx := context.Background()
	if _, err := db.Exec(ctx, `DELETE FROM world_messages`); err != nil {
		t.Fatalf("clean world_messages: %v", err)
	}
	t.Cleanup(func() {
		_, _ = db.Exec(context.Background(), `DELETE FROM world_messages`)
	})
}

func TestWorldDBListCursors(t *testing.T) {
	db := testDB(t)
	resetWorldMessages(t, db)
	uid := newTestUser(t, db)
	ctx := context.Background()

	ids := make([]int64, 5)
	for i := range ids {
		if err := db.QueryRow(ctx, `INSERT INTO world_messages (sender_id, sender_name, content, content_format)
			VALUES ($1, $2, $3, 'html') RETURNING id`, uid, uid, fmt.Sprintf("m%d", i)).Scan(&ids[i]); err != nil {
			t.Fatalf("insert message %d: %v", i, err)
		}
	}

	// 最新一页（降序），多取一条探测 has_more。
	items, hasMore, err := db.ListWorldMessages(ctx, 0, 0, 2)
	if err != nil {
		t.Fatalf("latest page: %v", err)
	}
	if !hasMore || len(items) != 2 || items[0].ID != ids[4] || items[1].ID != ids[3] {
		t.Fatalf("latest page = %+v hasMore=%v, want [%d,%d]", items, hasMore, ids[4], ids[3])
	}

	// before_id 向下翻页：取 ids[3] 之前的两条。
	items, hasMore, err = db.ListWorldMessages(ctx, ids[3], 0, 2)
	if err != nil {
		t.Fatalf("before page: %v", err)
	}
	if !hasMore || len(items) != 2 || items[0].ID != ids[2] || items[1].ID != ids[1] {
		t.Fatalf("before page = %+v hasMore=%v, want [%d,%d]", items, hasMore, ids[2], ids[1])
	}

	// 最老一条之前：空页、无更多。
	items, hasMore, err = db.ListWorldMessages(ctx, ids[0], 0, 2)
	if err != nil {
		t.Fatalf("before oldest: %v", err)
	}
	if hasMore || len(items) != 0 {
		t.Fatalf("before oldest = %+v hasMore=%v, want empty/false", items, hasMore)
	}

	// after_id 增量（升序）。
	items, hasMore, err = db.ListWorldMessages(ctx, 0, ids[1], 10)
	if err != nil {
		t.Fatalf("after page: %v", err)
	}
	if hasMore || len(items) != 3 || items[0].ID != ids[2] || items[2].ID != ids[4] {
		t.Fatalf("after page = %+v hasMore=%v, want ids[2..4]", items, hasMore)
	}

	// 同时提供时 after_id 优先。
	items, _, err = db.ListWorldMessages(ctx, ids[4], ids[0], 10)
	if err != nil {
		t.Fatalf("after+before: %v", err)
	}
	if len(items) != 4 || items[0].ID != ids[1] {
		t.Fatalf("after+before 应以 after 为准，got %+v", items)
	}

	// after_id 最新之后：空。
	items, hasMore, err = db.ListWorldMessages(ctx, 0, ids[4], 10)
	if err != nil {
		t.Fatalf("after newest: %v", err)
	}
	if hasMore || len(items) != 0 {
		t.Fatalf("after newest = %+v hasMore=%v", items, hasMore)
	}

	// ListWorldAfterID 与 after_id 一致。
	items, err = db.ListWorldAfterID(ctx, ids[2], 10)
	if err != nil {
		t.Fatalf("ListWorldAfterID: %v", err)
	}
	if len(items) != 2 || items[0].ID != ids[3] || items[1].ID != ids[4] {
		t.Fatalf("ListWorldAfterID = %+v, want [%d,%d]", items, ids[3], ids[4])
	}

	// limit 超过 500 被截断（数据量小，不报错且返回全部 5 条）。
	items, _, err = db.ListWorldMessages(ctx, 0, 0, 501)
	if err != nil {
		t.Fatalf("limit clamp: %v", err)
	}
	if len(items) != 5 {
		t.Fatalf("limit 501 截断后返回 %d 条, want 5", len(items))
	}

	// 空结果必须是 JSON 空数组而不是 nil。
	items, _, err = db.ListWorldMessages(ctx, ids[0], 0, 2)
	if err != nil {
		t.Fatalf("empty page: %v", err)
	}
	if items == nil {
		t.Fatal("空页应返回非 nil slice")
	}
}

func TestWorldDBCreateSnapshotAndRateLimit(t *testing.T) {
	db := testDB(t)
	resetWorldMessages(t, db)
	uid := newTestUser(t, db)
	ctx := context.Background()

	// 未入馆：会馆字段为空。
	snap, err := db.GetWorldUserSnapshot(ctx, uid)
	if err != nil {
		t.Fatalf("snapshot: %v", err)
	}
	if snap == nil || snap.UserID != uid || snap.GuildID != "" || snap.GuildName != "" || snap.IsLeader {
		t.Fatalf("未入馆快照 = %+v", snap)
	}

	// 建会馆并设为馆长，验证快照字段。
	var gid int64
	if err := db.QueryRow(ctx, `INSERT INTO guilds (slug, name, leader_user_id) VALUES ($1, $2, $3) RETURNING id`,
		"tw"+uid, "TW"+uid, uid).Scan(&gid); err != nil {
		t.Fatalf("insert guild: %v", err)
	}
	t.Cleanup(func() {
		_, _ = db.Exec(context.Background(), `DELETE FROM guild_members WHERE user_id = $1`, uid)
		_, _ = db.Exec(context.Background(), `DELETE FROM guilds WHERE id = $1`, gid)
	})
	if _, err := db.Exec(ctx, `INSERT INTO guild_members (user_id, guild_id) VALUES ($1, $2)`, uid, gid); err != nil {
		t.Fatalf("join guild: %v", err)
	}
	var guildUUID, guildName string
	if err := db.QueryRow(ctx, `SELECT uuid::text, name FROM guilds WHERE id = $1`, gid).Scan(&guildUUID, &guildName); err != nil {
		t.Fatalf("read guild: %v", err)
	}

	id, err := db.CreateWorldMessage(ctx, uid, "<p>hello</p>", "html", nil)
	if err != nil {
		t.Fatalf("create: %v", err)
	}
	var (
		name, avatar, gidText, gname string
		isLeader                     bool
	)
	if err := db.QueryRow(ctx, `SELECT sender_name, sender_avatar, guild_id, guild_name, is_leader
		FROM world_messages WHERE id = $1`, id).Scan(&name, &avatar, &gidText, &gname, &isLeader); err != nil {
		t.Fatalf("read created: %v", err)
	}
	if name != uid || avatar != "" || gidText != guildUUID || gname != guildName || !isLeader {
		t.Fatalf("快照 = name=%q avatar=%q guild=%q/%q leader=%v", name, avatar, gidText, gname, isLeader)
	}

	// 2 秒限流：紧接的第二条被拒。
	if _, err := db.CreateWorldMessage(ctx, uid, "<p>again</p>", "html", nil); !errors.Is(err, ErrWorldRateLimited) {
		t.Fatalf("second send err = %v, want ErrWorldRateLimited", err)
	}
}

func TestWorldDBCleanupKeepsNewest(t *testing.T) {
	db := testDB(t)
	resetWorldMessages(t, db)
	ctx := context.Background()

	if _, err := db.Exec(ctx, `INSERT INTO world_messages (sender_id, sender_name, content, content_format)
		SELECT 'TWCLEAN', '', 'x', 'html' FROM generate_series(1, 10050)`); err != nil {
		t.Fatalf("seed messages: %v", err)
	}
	var total int64
	if err := db.QueryRow(ctx, `SELECT COUNT(*) FROM world_messages`).Scan(&total); err != nil {
		t.Fatalf("count: %v", err)
	}
	if total != 10050 {
		t.Fatalf("seed total = %d, want 10050", total)
	}

	deleted, err := db.WorldCleanup(ctx)
	if err != nil {
		t.Fatalf("cleanup: %v", err)
	}
	if deleted != 50 {
		t.Fatalf("cleanup deleted = %d, want 50", deleted)
	}
	if err := db.QueryRow(ctx, `SELECT COUNT(*) FROM world_messages`).Scan(&total); err != nil {
		t.Fatalf("count after: %v", err)
	}
	if total != WorldKeepCount {
		t.Fatalf("cleanup 后剩余 %d 条, want %d", total, WorldKeepCount)
	}

	// 恰好保留数：再跑一次不应删除任何行。
	deleted, err = db.WorldCleanup(ctx)
	if err != nil {
		t.Fatalf("cleanup again: %v", err)
	}
	if deleted != 0 {
		t.Fatalf("second cleanup deleted = %d, want 0", deleted)
	}
}
