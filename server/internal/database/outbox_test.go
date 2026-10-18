package database

import (
	"context"
	"testing"
	"time"
)

func TestOutboxOneRowPerRecipientAndRetry(t *testing.T) {
	db := testDB(t)
	ctx, cancel := context.WithTimeout(context.Background(), 20*time.Second)
	defer cancel()

	marker := "outbox-test-" + GenID("")
	in := EmailOutboxInput{
		To:        []string{"a@example.test", "b@example.test"},
		Subject:   marker,
		PlainBody: "plain",
		HTMLBody:  "<p>html</p>",
		DedupeKey: marker,
	}
	n, err := db.EnqueueEmail(ctx, in)
	if err != nil {
		t.Fatalf("enqueue: %v", err)
	}
	if n != 2 {
		t.Fatalf("一邮多收插入 %d 行，期望 2（一行一收件人）", n)
	}
	if n, err = db.EnqueueEmail(ctx, in); err != nil || n != 0 {
		t.Fatalf("重复入队 = (%d,%v)，期望 (0,nil)", n, err)
	}

	batch, err := db.ClaimEmailBatch(ctx, 50)
	if err != nil {
		t.Fatalf("claim: %v", err)
	}
	ours := make([]OutboxEmail, 0, 2)
	for _, e := range batch {
		if e.Subject == marker {
			ours = append(ours, e)
		}
	}
	if len(ours) != 2 {
		t.Fatalf("认领到本测试邮件 %d 封，期望 2", len(ours))
	}
	for _, e := range ours {
		if e.Attempts != 1 {
			t.Fatalf("首次认领 attempts=%d，期望 1", e.Attempts)
		}
	}

	// 一封成功；另一封失败后按 retryAt 回队
	if err := db.MarkEmailSent(ctx, ours[0].ID); err != nil {
		t.Fatalf("mark sent: %v", err)
	}
	if err := db.MarkEmailFailed(ctx, ours[1].ID, "smtp down", time.Now().Add(-time.Second)); err != nil {
		t.Fatalf("mark failed retry: %v", err)
	}
	batch, err = db.ClaimEmailBatch(ctx, 50)
	if err != nil {
		t.Fatalf("claim retry: %v", err)
	}
	var retried *OutboxEmail
	for i := range batch {
		if batch[i].Subject == marker {
			retried = &batch[i]
		}
	}
	if retried == nil {
		t.Fatal("失败邮件未回到 pending 被重新认领")
	}
	if retried.Attempts != 2 {
		t.Fatalf("第二次认领 attempts=%d，期望 2", retried.Attempts)
	}

	// 退避到未来后不应被立刻认领
	if err := db.MarkEmailFailed(ctx, retried.ID, "retry later", time.Now().Add(time.Hour)); err != nil {
		t.Fatalf("mark failed future: %v", err)
	}
	batch, _ = db.ClaimEmailBatch(ctx, 50)
	for _, e := range batch {
		if e.Subject == marker {
			t.Fatal("退避未到期的邮件被提前认领")
		}
	}

	// 死信
	if err := db.MarkEmailFailed(ctx, retried.ID, "dead", time.Time{}); err != nil {
		t.Fatalf("mark dead: %v", err)
	}
	var status int
	if err := db.QueryRow(ctx, `SELECT status FROM email_outbox WHERE id=$1`, retried.ID).Scan(&status); err != nil {
		t.Fatalf("query status: %v", err)
	}
	if status != EmailStatusDead {
		t.Fatalf("死信 status=%d，期望 %d", status, EmailStatusDead)
	}
}

func TestCacheInvalidationClaimAndRetry(t *testing.T) {
	db := testDB(t)
	ctx, cancel := context.WithTimeout(context.Background(), 20*time.Second)
	defer cancel()
	key := "posts:list:1:" + GenID("")
	if err := db.EnqueueCacheInvalidation(ctx, "posts", key); err != nil {
		t.Fatalf("enqueue: %v", err)
	}
	// 同 scope+key 未处理时去重
	if err := db.EnqueueCacheInvalidation(ctx, "posts", key); err != nil {
		t.Fatalf("enqueue dup: %v", err)
	}
	items, err := db.ClaimCacheInvalidations(ctx, 50)
	if err != nil {
		t.Fatalf("claim: %v", err)
	}
	var item *CacheInvalidation
	for i := range items {
		if items[i].Key == key {
			item = &items[i]
		}
	}
	if item == nil {
		t.Fatal("未认领到 cache invalidation")
	}
	if item.Attempts != 1 {
		t.Fatalf("首次 attempts=%d，期望 1", item.Attempts)
	}
	// 失败后仍可重试
	if err := db.MarkCacheInvalidation(ctx, item.ID, "boom"); err != nil {
		t.Fatalf("mark failed: %v", err)
	}
	items, _ = db.ClaimCacheInvalidations(ctx, 50)
	found := false
	for _, it := range items {
		if it.ID == item.ID {
			found = true
			if it.Attempts != 2 {
				t.Fatalf("重试 attempts=%d，期望 2", it.Attempts)
			}
		}
	}
	if !found {
		t.Fatal("失败任务未被重新认领")
	}
	// 成功后 processed_at 置位
	if err := db.MarkCacheInvalidation(ctx, item.ID, ""); err != nil {
		t.Fatalf("mark done: %v", err)
	}
	var processed *time.Time
	if err := db.QueryRow(ctx, `SELECT processed_at FROM cache_invalidations WHERE id=$1`, item.ID).Scan(&processed); err != nil {
		t.Fatalf("query processed: %v", err)
	}
	if processed == nil {
		t.Fatal("成功任务 processed_at 仍为 NULL")
	}
}

func TestListFollowerEmailsFilters(t *testing.T) {
	db := testDB(t)
	ctx, cancel := context.WithTimeout(context.Background(), 20*time.Second)
	defer cancel()
	author := newTestUser(t, db)
	normal := newTestUser(t, db)
	banned := newTestUser(t, db)
	unverified := newTestUser(t, db)
	deleted := newTestUser(t, db)

	if _, err := db.Exec(ctx, `UPDATE users SET is_banned=1 WHERE id=$1`, banned); err != nil {
		t.Fatalf("ban: %v", err)
	}
	if _, err := db.Exec(ctx, `UPDATE users SET email_verified=0 WHERE id=$1`, unverified); err != nil {
		t.Fatalf("unverify: %v", err)
	}
	if _, err := db.Exec(ctx, `UPDATE users SET deleted_at=NOW() WHERE id=$1`, deleted); err != nil {
		t.Fatalf("delete: %v", err)
	}
	for _, follower := range []string{normal, banned, unverified, deleted} {
		if _, err := db.Exec(ctx, `INSERT INTO user_follows (follower_id, following_id) VALUES ($1,$2)`, follower, author); err != nil {
			t.Fatalf("follow: %v", err)
		}
	}
	emails, err := db.ListFollowerEmails(ctx, author, 100)
	if err != nil {
		t.Fatalf("list follower emails: %v", err)
	}
	if len(emails) != 1 || emails[0] != normal+"@example.test" {
		t.Fatalf("粉丝邮箱 = %v，期望仅 %s", emails, normal+"@example.test")
	}
}
