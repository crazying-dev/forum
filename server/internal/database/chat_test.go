package database

import (
	"context"
	"testing"
	"time"
)

func TestChatRoomUnreadAndRead(t *testing.T) {
	db := testDB(t)
	uid := newTestUser(t, db)
	ctx, cancel := context.WithTimeout(context.Background(), 20*time.Second)
	defer cancel()

	room1, err := db.EnsureChatRoom(ctx, uid)
	if err != nil {
		t.Fatalf("ensure room: %v", err)
	}
	room2, err := db.EnsureChatRoom(ctx, uid)
	if err != nil || room1 != room2 {
		t.Fatalf("EnsureChatRoom 非幂等: %d/%d err=%v", room1, room2, err)
	}

	msg, err := db.CreateChatMessage(ctx, uid, "<p>你好</p>")
	if err != nil {
		t.Fatalf("create chat message: %v", err)
	}
	if msg.ID <= 0 || msg.SenderType != "user" || msg.ContentHTML != "<p>你好</p>" {
		t.Fatalf("chat message = %+v", msg)
	}
	// 自己发的消息不计未读
	if unread, err := db.ChatUnread(ctx, uid); err != nil || unread != 0 {
		t.Fatalf("own message unread=(%d,%v)，期望 0", unread, err)
	}

	// 模拟管理员回复
	var adminMsgID int64
	if err := db.QueryRow(ctx, `INSERT INTO chat_messages (room_id, sender_type, admin_id, content_html)
		VALUES ($1, 'admin', 'admin001', '<p>回复</p>') RETURNING id`, room1).Scan(&adminMsgID); err != nil {
		t.Fatalf("insert admin message: %v", err)
	}
	if unread, err := db.ChatUnread(ctx, uid); err != nil || unread != 1 {
		t.Fatalf("admin message unread=(%d,%v)，期望 1", unread, err)
	}

	items, hasMore, err := db.GetChatMessages(ctx, uid, "", 20)
	if err != nil || len(items) != 2 || hasMore {
		t.Fatalf("chat list=(%d,%v,%v)，期望 2,false,nil", len(items), hasMore, err)
	}
	if items[0].ID != adminMsgID || items[0].SenderType != "admin" {
		t.Fatalf("最新消息 = %+v，期望管理员回复", items[0])
	}

	if err := db.MarkChatRead(ctx, uid, adminMsgID); err != nil {
		t.Fatalf("mark chat read: %v", err)
	}
	if unread, _ := db.ChatUnread(ctx, uid); unread != 0 {
		t.Fatalf("已读后 unread=%d，期望 0", unread)
	}
	counts, err := db.UnreadCounts(ctx, uid)
	if err != nil || counts.Chat != 0 {
		t.Fatalf("summary chat=(%d,%v)，期望 0", counts.Chat, err)
	}
}
