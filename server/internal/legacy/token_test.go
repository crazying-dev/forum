package legacy

import (
	"errors"
	"testing"
	"time"
)

func TestLegacyTokenRoundTrip(t *testing.T) {
	secret := "test-secret-key"
	uid := "RL0123456789ABCDEF"
	hash := "scrypt:32768:8:1$abcd$0123456789abcdef"
	now := time.Now()
	tok, err := GenerateToken(secret, uid, hash, now)
	if err != nil {
		t.Fatal(err)
	}
	v := NewTokenVerifier(secret, 7*24*time.Hour, time.Time{})
	if err := v.Verify(uid, tok, hash, time.Time{}, now); err != nil {
		t.Fatalf("valid token rejected: %v", err)
	}
}

func TestLegacyTokenExpired(t *testing.T) {
	secret := "test-secret-key"
	uid := "RL0123456789ABCDEF"
	hash := "pbkdf2:sha256:600000$salt$hash"
	old := time.Now().Add(-8 * 24 * time.Hour)
	tok, _ := GenerateToken(secret, uid, hash, old)
	v := NewTokenVerifier(secret, 7*24*time.Hour, time.Time{})
	if err := v.Verify(uid, tok, hash, time.Time{}, time.Now()); !errors.Is(err, ErrLegacyTokenExpired) {
		t.Fatalf("expected expired, got %v", err)
	}
}

func TestLegacyTokenFutureRejected(t *testing.T) {
	secret := "test-secret-key"
	uid := "RL0123456789ABCDEF"
	hash := "hash"
	future := time.Now().Add(time.Hour)
	tok, _ := GenerateToken(secret, uid, hash, future)
	v := NewTokenVerifier(secret, 7*24*time.Hour, time.Time{})
	if err := v.Verify(uid, tok, hash, time.Time{}, time.Now()); !errors.Is(err, ErrLegacyTokenFuture) {
		t.Fatalf("expected future, got %v", err)
	}
}

func TestLegacyTokenPasswordChangedRejected(t *testing.T) {
	secret := "test-secret-key"
	uid := "RL0123456789ABCDEF"
	hash := "hash"
	sent := time.Now().Add(-time.Hour)
	tok, _ := GenerateToken(secret, uid, hash, sent)
	v := NewTokenVerifier(secret, 7*24*time.Hour, time.Time{})
	if err := v.Verify(uid, tok, hash, time.Now().Add(-30*time.Minute), time.Now()); !errors.Is(err, ErrLegacyTokenExpired) {
		t.Fatalf("expected password-change cutoff, got %v", err)
	}
}

func TestLegacyTokenTamperedRejected(t *testing.T) {
	secret := "test-secret-key"
	uid := "RL0123456789ABCDEF"
	hash := "hash"
	tok, _ := GenerateToken(secret, uid, hash, time.Now())
	v := NewTokenVerifier(secret, 7*24*time.Hour, time.Time{})
	if err := v.Verify(uid, tok+"x", hash, time.Time{}, time.Now()); err == nil {
		t.Fatal("tampered token accepted")
	}
}
