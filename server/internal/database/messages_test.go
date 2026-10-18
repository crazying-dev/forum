package database

import (
	"context"
	"testing"
	"time"
)

func newTestPost(t *testing.T, db *DB, authorID, title string) string {
	t.Helper()
	id := GenID("TP")
	if _, err := db.Exec(context.Background(), `INSERT INTO posts (id, user_id, title, content)
		VALUES ($1, $2, $3, '<p>正文</p>')`, id, authorID, title); err != nil {
		t.Fatalf("insert post: %v", err)
	}
	t.Cleanup(func() { _, _ = db.Exec(context.Background(), "DELETE FROM posts WHERE id=$1", id) })
	return id
}

func newTestComment(t *testing.T, db *DB, postID, authorID, content string, parentID *string) string {
	t.Helper()
	id := GenID("TC")
	if _, err := db.Exec(context.Background(), `INSERT INTO comments (id, post_id, user_id, content, content_format, parent_id)
		VALUES ($1, $2, $3, $4, 'html', $5)`, id, postID, authorID, content, parentID); err != nil {
		t.Fatalf("insert comment: %v", err)
	}
	t.Cleanup(func() { _, _ = db.Exec(context.Background(), "DELETE FROM comments WHERE id=$1", id) })
	return id
}

func TestLikeMessagesCursorPagination(t *testing.T) {
	db := testDB(t)
	recipient := newTestUser(t, db)
	actor := newTestUser(t, db)
	ctx, cancel := context.WithTimeout(context.Background(), 20*time.Second)
	defer cancel()

	// 3 个帖子赞 + 2 个评论赞（全部历史 union）
	for i := 0; i < 3; i++ {
		postID := newTestPost(t, db, recipient, "我的帖子"+itoa(i))
		if _, err := db.Exec(ctx, `INSERT INTO post_likes (post_id, user_id) VALUES ($1,$2)`, postID, actor); err != nil {
			t.Fatalf("insert post like: %v", err)
		}
	}
	postByActor := newTestPost(t, db, actor, "别人的帖子")
	for i := 0; i < 2; i++ {
		commentID := newTestComment(t, db, postByActor, recipient, "我的评论"+itoa(i), nil)
		if _, err := db.Exec(ctx, `INSERT INTO comment_likes (comment_id, user_id) VALUES ($1,$2)`, commentID, actor); err != nil {
			t.Fatalf("insert comment like: %v", err)
		}
	}

	seen := map[string]bool{}
	postLikes, commentLikes := 0, 0
	cursor := ""
	for page := 0; page < 3; page++ {
		items, hasMore, next, err := db.ListLikeMessages(ctx, recipient, cursor, 2)
		if err != nil {
			t.Fatalf("page %d: %v", page, err)
		}
		if page < 2 && !hasMore {
			t.Fatalf("第 %d 页 has_more=false，期望 true", page)
		}
		if page == 2 && hasMore {
			t.Fatalf("最后一页 has_more=true，期望 false")
		}
		for _, item := range items {
			if seen[item.ID] {
				t.Fatalf("cursor 分页出现重复 id=%s", item.ID)
			}
			seen[item.ID] = true
			switch item.TargetType {
			case "post":
				postLikes++
			case "comment":
				commentLikes++
			}
		}
		cursor = next
	}
	if len(seen) != 5 || postLikes != 3 || commentLikes != 2 {
		t.Fatalf("共 %d 条 (post=%d comment=%d)，期望 5(3/2)", len(seen), postLikes, commentLikes)
	}

	if _, _, _, err := db.ListLikeMessages(ctx, recipient, "not-a-cursor", 2); err == nil {
		t.Fatal("非法 cursor 应返回错误")
	}
}

func TestCommentMessagesCursorPagination(t *testing.T) {
	db := testDB(t)
	recipient := newTestUser(t, db)
	actor := newTestUser(t, db)
	ctx, cancel := context.WithTimeout(context.Background(), 20*time.Second)
	defer cancel()

	myPost := newTestPost(t, db, recipient, "我的帖子")
	for i := 0; i < 3; i++ {
		newTestComment(t, db, myPost, actor, "评论"+itoa(i), nil)
	}
	// 对我的评论的回复（帖子属于 actor）
	otherPost := newTestPost(t, db, actor, "别人的帖子")
	myComment := newTestComment(t, db, otherPost, recipient, "我的评论", nil)
	newTestComment(t, db, otherPost, actor, "回复我", &myComment)
	// 我自己的评论不应出现
	newTestComment(t, db, myPost, recipient, "自己评论自己", nil)

	page1, hasMore, next, err := db.ListCommentMessages(ctx, recipient, "", 2)
	if err != nil || len(page1) != 2 || !hasMore || next == "" {
		t.Fatalf("第一页 = (%d,%v,%q,%v)，期望 2,true,非空,nil", len(page1), hasMore, next, err)
	}
	page2, hasMore, _, err := db.ListCommentMessages(ctx, recipient, next, 2)
	if err != nil || len(page2) != 2 || hasMore {
		t.Fatalf("第二页 = (%d,%v,%v)，期望 2,false,nil", len(page2), hasMore, err)
	}
	ids := map[string]bool{}
	for _, m := range append(page1, page2...) {
		if ids[m.ID] {
			t.Fatalf("重复评论消息 id=%s", m.ID)
		}
		ids[m.ID] = true
	}
	if len(ids) != 4 {
		t.Fatalf("评论消息总数 = %d，期望 4（3 评论 + 1 回复）", len(ids))
	}
}
