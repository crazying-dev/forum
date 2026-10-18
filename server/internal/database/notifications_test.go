package database

import (
	"context"
	"testing"
	"time"
)

func TestListSystemAndBroadcastPagination(t *testing.T) {
	db := testDB(t)
	uid := newTestUser(t, db)
	ctx, cancel := context.WithTimeout(context.Background(), 20*time.Second)
	defer cancel()

	var broadcastID int64
	if err := db.QueryRow(ctx, `INSERT INTO broadcast_notices (type, title, body_html, link)
		VALUES ('notice', '公告', '<p>正文</p>', '/notice') RETURNING id`).Scan(&broadcastID); err != nil {
		t.Fatalf("insert broadcast: %v", err)
	}
	for i := 0; i < 2; i++ {
		if _, ok, err := db.CreateNotification(ctx, NotificationInput{
			UserID: uid, Type: NotificationSystem,
			Payload:   map[string]any{"title": "系统消息", "body_html": "<p>body</p>", "link": "/x"},
			DedupeKey: "system:" + uid + ":" + itoa(i),
		}); err != nil || !ok {
			t.Fatalf("create system notification %d: ok=%v err=%v", i, ok, err)
		}
	}

	page1, hasMore, next, err := db.ListSystem(ctx, uid, "", 2)
	if err != nil {
		t.Fatalf("list system page1: %v", err)
	}
	if len(page1) != 2 || !hasMore || next == "" {
		t.Fatalf("page1=(%d,%v,%q)，期望 2,true,非空", len(page1), hasMore, next)
	}
	page2, hasMore, _, err := db.ListSystem(ctx, uid, next, 2)
	if err != nil {
		t.Fatalf("list system page2: %v", err)
	}
	if len(page2) != 1 || hasMore {
		t.Fatalf("page2=(%d,%v)，期望 1,false", len(page2), hasMore)
	}
	seen := map[string]bool{}
	for _, m := range append(page1, page2...) {
		key := SystemCursor(m.CreatedAt, m.Source, m.ID)
		if seen[key] {
			t.Fatalf("系统消息分页重复: %+v", m)
		}
		seen[key] = true
	}
	if len(seen) != 3 {
		t.Fatalf("系统消息总数 = %d，期望 3（1 广播 + 2 用户）", len(seen))
	}

	list, hasMore, err := db.BroadcastList(ctx, "", 20)
	if err != nil || len(list) != 1 || hasMore || list[0].ID != broadcastID {
		t.Fatalf("BroadcastList=(%d,%v,%v)，期望 1 条", len(list), hasMore, err)
	}
}

func TestCreateNotificationDedupeAndUnread(t *testing.T) {
	db := testDB(t)
	recipient := newTestUser(t, db)
	actor := newTestUser(t, db)
	ctx, cancel := context.WithTimeout(context.Background(), 20*time.Second)
	defer cancel()

	// 先标记已读到一个过去时间点，确保后续通知计入未读
	if err := db.MarkRead(ctx, recipient, "likes", time.Now().Add(-time.Minute)); err != nil {
		t.Fatalf("mark read: %v", err)
	}

	in := NotificationInput{
		UserID: recipient, Type: NotificationPostLike, ActorID: actor,
		TargetType: "post", TargetID: "P-dedupe-" + recipient, ContextPostID: "P-dedupe-" + recipient,
		Payload:   map[string]any{"post_title": "标题"},
		DedupeKey: "post_like:" + recipient + ":" + actor,
	}
	id1, created1, err := db.CreateNotification(ctx, in)
	if err != nil {
		t.Fatalf("create notification: %v", err)
	}
	if !created1 || id1 <= 0 {
		t.Fatalf("首次通知 = (%d,%v)，期望 id>0,created", id1, created1)
	}
	id2, created2, err := db.CreateNotification(ctx, in)
	if err != nil {
		t.Fatalf("repeat notification: %v", err)
	}
	if created2 || id2 != 0 {
		t.Fatalf("重复 dedupe_key 通知 = (%d,%v)，期望 (0,false)", id2, created2)
	}
	var count int
	if err := db.QueryRow(ctx, `SELECT COUNT(*) FROM notifications WHERE user_id=$1 AND type='post_like'`, recipient).Scan(&count); err != nil {
		t.Fatalf("count notifications: %v", err)
	}
	if count != 1 {
		t.Fatalf("通知行数 = %d，期望 1", count)
	}

	// 未读只统计 last_read_at 之后：先 +1，标记已读后归零，再来一条再 +1
	counts, err := db.UnreadCounts(ctx, recipient)
	if err != nil {
		t.Fatalf("unread counts: %v", err)
	}
	if counts.Likes != 1 {
		t.Fatalf("likes 未读 = %d，期望 1", counts.Likes)
	}
	if err := db.MarkCategoryRead(ctx, recipient, "likes", time.Now().Add(time.Second)); err != nil {
		t.Fatalf("mark category read: %v", err)
	}
	counts, _ = db.UnreadCounts(ctx, recipient)
	if counts.Likes != 0 {
		t.Fatalf("标记已读后 likes 未读 = %d，期望 0", counts.Likes)
	}

	// 空 dedupe_key 不去重（允许系统批量写入）；先标系统已读，避免全局广播干扰断言
	if err := db.MarkCategoryRead(ctx, recipient, "system", time.Now()); err != nil {
		t.Fatalf("mark system read: %v", err)
	}
	time.Sleep(5 * time.Millisecond) // 确保新通知 created_at 晚于 last_read_at
	in2 := in
	in2.DedupeKey = ""
	in2.Type = NotificationSystem
	if _, ok, err := db.CreateNotification(ctx, in2); err != nil || !ok {
		t.Fatalf("空 dedupe 通知失败: ok=%v err=%v", ok, err)
	}
	if _, ok, _ := db.CreateNotification(ctx, in2); !ok {
		t.Fatal("空 dedupe_key 的重复通知应各自落行")
	}
	counts, _ = db.UnreadCounts(ctx, recipient)
	if counts.System != 2 {
		t.Fatalf("system 未读 = %d，期望 2", counts.System)
	}
}
