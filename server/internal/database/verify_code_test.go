package database

import (
	"context"
	"fmt"
	"testing"
	"time"
)

func testVerifyEmail(t *testing.T) string {
	t.Helper()
	return fmt.Sprintf("vcode-%d@example.com", time.Now().UnixNano())
}

// 新码下发必须作废旧码，避免多码并存放大爆破命中率。
func TestCreateVerifyCodeInvalidatesPrevious(t *testing.T) {
	db := testDB(t)
	ctx := context.Background()
	email := testVerifyEmail(t)
	t.Cleanup(func() { _, _ = db.Exec(context.Background(), `DELETE FROM verify_codes WHERE email=$1`, email) })

	if err := db.CreateVerifyCode(ctx, email, "111111", "register", 5); err != nil {
		t.Fatalf("create first code: %v", err)
	}
	if err := db.CreateVerifyCode(ctx, email, "222222", "register", 5); err != nil {
		t.Fatalf("create second code: %v", err)
	}

	if ok, err := db.GetVerifyCode(ctx, email, "111111", "register"); err != nil || ok {
		t.Fatalf("old code should be invalidated, ok=%v err=%v", ok, err)
	}
	if ok, err := db.GetVerifyCode(ctx, email, "222222", "register"); err != nil || !ok {
		t.Fatalf("latest code should be valid, ok=%v err=%v", ok, err)
	}
}

// 核销必须原子且一次性：并发重复提交只允许成功一次。
func TestConsumeVerifyCodeOnce(t *testing.T) {
	db := testDB(t)
	ctx := context.Background()
	email := testVerifyEmail(t)
	t.Cleanup(func() { _, _ = db.Exec(context.Background(), `DELETE FROM verify_codes WHERE email=$1`, email) })

	if err := db.CreateVerifyCode(ctx, email, "333333", "reset_password", 5); err != nil {
		t.Fatalf("create code: %v", err)
	}
	ok, err := db.ConsumeVerifyCode(ctx, email, "333333", "reset_password")
	if err != nil || !ok {
		t.Fatalf("first consume should succeed, ok=%v err=%v", ok, err)
	}
	ok, err = db.ConsumeVerifyCode(ctx, email, "333333", "reset_password")
	if err != nil || ok {
		t.Fatalf("second consume should fail, ok=%v err=%v", ok, err)
	}
	if valid, err := db.GetVerifyCode(ctx, email, "333333", "reset_password"); err != nil || valid {
		t.Fatalf("consumed code should be invalid, valid=%v err=%v", valid, err)
	}
}

// 失败次数达上限后作废当前码，计数归零。
func TestVerifyCodeAttemptsInvalidate(t *testing.T) {
	db := testDB(t)
	ctx := context.Background()
	email := testVerifyEmail(t)
	t.Cleanup(func() { _, _ = db.Exec(context.Background(), `DELETE FROM verify_codes WHERE email=$1`, email) })

	if err := db.CreateVerifyCode(ctx, email, "444444", "change_password", 5); err != nil {
		t.Fatalf("create code: %v", err)
	}
	for i := 0; i < 5; i++ {
		if err := db.BumpActiveVerifyCodeAttempts(ctx, email, "change_password"); err != nil {
			t.Fatalf("bump attempts: %v", err)
		}
	}
	if n, err := db.GetActiveVerifyCodeAttempts(ctx, email, "change_password"); err != nil || n != 5 {
		t.Fatalf("attempts = %d, err=%v, want 5", n, err)
	}
	if err := db.InvalidateActiveVerifyCodes(ctx, email, "change_password"); err != nil {
		t.Fatalf("invalidate: %v", err)
	}
	if n, err := db.GetActiveVerifyCodeAttempts(ctx, email, "change_password"); err != nil || n != 0 {
		t.Fatalf("attempts after invalidate = %d, err=%v, want 0", n, err)
	}
	if ok, err := db.GetVerifyCode(ctx, email, "444444", "change_password"); err != nil || ok {
		t.Fatalf("code should be invalid after invalidate, ok=%v err=%v", ok, err)
	}
}
