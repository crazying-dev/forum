package database

import (
	"context"
	"testing"
	"time"
)

func TestAwardSpiritDedupeAndDailyCap(t *testing.T) {
	db := testDB(t)
	uid := newTestUser(t, db)
	ctx, cancel := context.WithTimeout(context.Background(), 20*time.Second)
	defer cancel()

	// 重复 source 只奖励一次
	awarded, amount, err := db.AwardSpirit(ctx, uid, "post", "src-post-1-"+uid)
	if err != nil {
		t.Fatalf("award post: %v", err)
	}
	if !awarded || amount != 5 {
		t.Fatalf("首次发帖奖励 = (%v,%d)，期望 (true,5)", awarded, amount)
	}
	awarded, amount, err = db.AwardSpirit(ctx, uid, "post", "src-post-1-"+uid)
	if err != nil {
		t.Fatalf("repeat award: %v", err)
	}
	if awarded || amount != 0 {
		t.Fatalf("重复 source 奖励 = (%v,%d)，期望 (false,0)", awarded, amount)
	}

	// 发帖日上限 20：再发 3 篇到顶，第 5 篇不再奖励
	for i := 2; i <= 4; i++ {
		a, n, e := db.AwardSpirit(ctx, uid, "post", "src-post-"+itoa(i)+"-"+uid)
		if e != nil || !a || n != 5 {
			t.Fatalf("第 %d 篇发帖奖励 = (%v,%d,%v)，期望 (true,5,nil)", i, a, n, e)
		}
	}
	awarded, amount, err = db.AwardSpirit(ctx, uid, "post", "src-post-5-"+uid)
	if err != nil {
		t.Fatalf("cap award: %v", err)
	}
	if awarded || amount != 0 {
		t.Fatalf("超过日上限 = (%v,%d)，期望 (false,0)", awarded, amount)
	}

	// 评论日上限 15：5 条到顶，第 6 条不再奖励
	for i := 1; i <= 5; i++ {
		a, n, e := db.AwardSpirit(ctx, uid, "comment", "src-comment-"+itoa(i)+"-"+uid)
		if e != nil || !a || n != 3 {
			t.Fatalf("第 %d 条评论奖励 = (%v,%d,%v)，期望 (true,3,nil)", i, a, n, e)
		}
	}
	awarded, _, err = db.AwardSpirit(ctx, uid, "comment", "src-comment-6-"+uid)
	if err != nil {
		t.Fatalf("comment cap: %v", err)
	}
	if awarded {
		t.Fatal("评论超过日上限仍发放了")
	}

	var spirit int
	if err := db.QueryRow(ctx, `SELECT spirit FROM users WHERE id = $1`, uid).Scan(&spirit); err != nil {
		t.Fatalf("query spirit: %v", err)
	}
	if spirit != 35 {
		t.Fatalf("最终灵力 = %d，期望 35（20 发帖 + 15 评论）", spirit)
	}
	var postUsed, commentUsed int
	if err := db.QueryRow(ctx, `SELECT COALESCE(SUM(awarded),0) FROM spirit_daily_usage WHERE user_id=$1 AND action='post'`, uid).Scan(&postUsed); err != nil {
		t.Fatalf("query post usage: %v", err)
	}
	if err := db.QueryRow(ctx, `SELECT COALESCE(SUM(awarded),0) FROM spirit_daily_usage WHERE user_id=$1 AND action='comment'`, uid).Scan(&commentUsed); err != nil {
		t.Fatalf("query comment usage: %v", err)
	}
	if postUsed != 20 || commentUsed != 15 {
		t.Fatalf("日用量 post=%d comment=%d，期望 20/15", postUsed, commentUsed)
	}
}
