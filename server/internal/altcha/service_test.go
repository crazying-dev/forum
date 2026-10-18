package altcha

import (
	"context"
	"encoding/base64"
	"encoding/json"
	"errors"
	"strings"
	"sync"
	"testing"
	"time"

	altchalib "github.com/altcha-org/altcha-lib-go/v2"
)

type memStore struct {
	mu   sync.Mutex
	used map[string]time.Time
}

func newMemStore() *memStore {
	return &memStore{used: make(map[string]time.Time)}
}

func (m *memStore) Consume(_ context.Context, challengeID string, expiresAt time.Time) (bool, error) {
	m.mu.Lock()
	defer m.mu.Unlock()
	if _, ok := m.used[challengeID]; ok {
		return false, nil
	}
	m.used[challengeID] = expiresAt
	return true, nil
}

func newTestService() *Service {
	svc := New(nil, Config{
		Enabled:   true,
		HMACKey:   "test-hmac-key",
		Algorithm: DefaultAlgorithm,
		Cost:      10,
		Expires:   time.Minute,
	})
	svc.store = newMemStore()
	svc.randInt = func(int) int { return 0 }
	return svc
}

func solvePayload(t *testing.T, svc *Service) (altchalib.Payload, string) {
	t.Helper()
	challenge, err := svc.Challenge(context.Background())
	if err != nil {
		t.Fatalf("Challenge() error = %v", err)
	}
	solution, err := altchalib.SolveChallenge(altchalib.SolveChallengeOptions{
		Challenge:   challenge,
		DeriveKey:   altchalib.DeriveKeyPBKDF2(),
		CounterStep: 1,
	})
	if err != nil || solution == nil {
		t.Fatalf("SolveChallenge() = %v, %v", solution, err)
	}
	payload := altchalib.Payload{Challenge: challenge, Solution: *solution}
	raw, err := json.Marshal(payload)
	if err != nil {
		t.Fatalf("marshal payload: %v", err)
	}
	return payload, base64.StdEncoding.EncodeToString(raw)
}

func TestChallengeVerifyAndReplay(t *testing.T) {
	svc := newTestService()
	_, encoded := solvePayload(t, svc)

	ok, err := svc.Verify(context.Background(), encoded)
	if err != nil || !ok {
		t.Fatalf("first Verify() = %v, %v; want true, nil", ok, err)
	}
	ok, err = svc.Verify(context.Background(), encoded)
	if err != nil {
		t.Fatalf("replay Verify() error = %v", err)
	}
	if ok {
		t.Fatal("replayed payload must not verify")
	}
}

func TestChallengeTampered(t *testing.T) {
	svc := newTestService()
	payload, encoded := solvePayload(t, svc)
	_ = encoded

	// 篡改挑战参数（cost）后签名不匹配。
	payload.Challenge.Parameters.Cost++
	raw, _ := json.Marshal(payload)
	ok, err := svc.Verify(context.Background(), base64.StdEncoding.EncodeToString(raw))
	if err != nil {
		t.Fatalf("tampered challenge Verify() error = %v", err)
	}
	if ok {
		t.Fatal("tampered challenge must not verify")
	}

	// 篡改 solution 的 derivedKey。
	payload, encoded = solvePayload(t, svc)
	_ = encoded
	if payload.Solution.DerivedKey == "" {
		t.Fatal("derivedKey is empty")
	}
	flipped := []byte(payload.Solution.DerivedKey)
	if flipped[0] == '0' {
		flipped[0] = '1'
	} else {
		flipped[0] = '0'
	}
	payload.Solution.DerivedKey = string(flipped)
	raw, _ = json.Marshal(payload)
	ok, err = svc.Verify(context.Background(), base64.StdEncoding.EncodeToString(raw))
	if err != nil {
		t.Fatalf("tampered solution Verify() error = %v", err)
	}
	if ok {
		t.Fatal("tampered solution must not verify")
	}
}

func TestChallengeExpired(t *testing.T) {
	svc := newTestService()
	svc.expires = -time.Minute
	_, encoded := solvePayload(t, svc)

	ok, err := svc.Verify(context.Background(), encoded)
	if err != nil {
		t.Fatalf("expired Verify() error = %v", err)
	}
	if ok {
		t.Fatal("expired challenge must not verify")
	}
}

func TestGrantLifecycle(t *testing.T) {
	svc := New(nil, Config{Enabled: true, HMACKey: "grant-secret"})
	now := time.Unix(1_700_000_000, 0)
	svc.now = func() time.Time { return now }

	token, err := svc.Grant()
	if err != nil {
		t.Fatalf("Grant() error = %v", err)
	}
	if !svc.VerifyGrant(token) {
		t.Fatal("fresh grant must verify")
	}

	// 未到期仍有效。
	now = now.Add(GrantTTL - time.Second)
	if !svc.VerifyGrant(token) {
		t.Fatal("grant must be valid before expiry")
	}

	// 过期失效。
	now = now.Add(2 * time.Second)
	if svc.VerifyGrant(token) {
		t.Fatal("expired grant must not verify")
	}
}

func TestGrantTampered(t *testing.T) {
	svc := New(nil, Config{Enabled: true, HMACKey: "grant-secret"})
	token, err := svc.Grant()
	if err != nil {
		t.Fatalf("Grant() error = %v", err)
	}
	parts := strings.Split(token, ".")
	if len(parts) != 2 {
		t.Fatalf("unexpected grant format: %q", token)
	}

	cases := []string{
		"",
		"garbage",
		parts[0] + "." + strings.Repeat("A", len(parts[1])),
		parts[0] + "x." + parts[1],
	}
	for _, bad := range cases {
		if svc.VerifyGrant(bad) {
			t.Errorf("VerifyGrant(%q) = true, want false", bad)
		}
	}

	// 不同 key 签发的 token 不能通过。
	other := New(nil, Config{Enabled: true, HMACKey: "other-secret"})
	otherToken, _ := other.Grant()
	if svc.VerifyGrant(otherToken) {
		t.Fatal("grant signed with another key must not verify")
	}
}

func TestFailClosed(t *testing.T) {
	ctx := context.Background()

	// 未启用：跳过校验。
	disabled := New(nil, Config{Enabled: false})
	if disabled.Enabled() {
		t.Fatal("disabled service must report Enabled()=false")
	}
	if _, err := disabled.Challenge(ctx); !errors.Is(err, ErrDisabled) {
		t.Fatalf("disabled Challenge() error = %v", err)
	}
	if _, err := disabled.Verify(ctx, "x"); !errors.Is(err, ErrDisabled) {
		t.Fatalf("disabled Verify() error = %v", err)
	}
	if _, err := disabled.Grant(); !errors.Is(err, ErrDisabled) {
		t.Fatalf("disabled Grant() error = %v", err)
	}
	if disabled.VerifyGrant("x") {
		t.Fatal("disabled VerifyGrant() must be false")
	}

	// 启用但缺 HMAC key：仍然 Enabled（调用方必须继续要求校验），操作全部失败。
	misconfigured := New(nil, Config{Enabled: true, HMACKey: ""})
	if !misconfigured.Enabled() {
		t.Fatal("enabled service must report Enabled()=true even without key")
	}
	if _, err := misconfigured.Challenge(ctx); !errors.Is(err, ErrNotConfigured) {
		t.Fatalf("misconfigured Challenge() error = %v", err)
	}
	if _, err := misconfigured.Verify(ctx, "x"); !errors.Is(err, ErrNotConfigured) {
		t.Fatalf("misconfigured Verify() error = %v", err)
	}
	if _, err := misconfigured.Grant(); !errors.Is(err, ErrNotConfigured) {
		t.Fatalf("misconfigured Grant() error = %v", err)
	}
	if misconfigured.VerifyGrant("x") {
		t.Fatal("misconfigured VerifyGrant() must be false")
	}

	// 启用且签名有效，但没有消费存储：verify 必须失败（不能放行）。
	svc := New(nil, Config{Enabled: true, HMACKey: "key", Cost: 10, Expires: time.Minute})
	svc.randInt = func(int) int { return 0 }
	payload, encoded := solvePayload(t, svc)
	_ = payload
	if _, err := svc.Verify(ctx, encoded); !errors.Is(err, ErrNotConfigured) {
		t.Fatalf("Verify() without store error = %v, want ErrNotConfigured", err)
	}
}

func TestNilService(t *testing.T) {
	var svc *Service
	if svc.Enabled() {
		t.Fatal("nil service Enabled() must be false")
	}
	if svc.Algorithm() != DefaultAlgorithm || svc.Cost() != DefaultCost {
		t.Fatal("nil service getters must return defaults")
	}
	if _, err := svc.Challenge(context.Background()); !errors.Is(err, ErrDisabled) {
		t.Fatalf("nil Challenge() error = %v", err)
	}
	if _, err := svc.Verify(context.Background(), "x"); !errors.Is(err, ErrDisabled) {
		t.Fatalf("nil Verify() error = %v", err)
	}
	if _, err := svc.Grant(); !errors.Is(err, ErrDisabled) {
		t.Fatalf("nil Grant() error = %v", err)
	}
	if svc.VerifyGrant("x") {
		t.Fatal("nil VerifyGrant() must be false")
	}
}

func TestVerifyRejectsMalformedPayload(t *testing.T) {
	svc := newTestService()
	for _, bad := range []string{"", "!!!", base64.StdEncoding.EncodeToString([]byte("not json"))} {
		ok, err := svc.Verify(context.Background(), bad)
		if ok {
			t.Errorf("Verify(%q) = true, want false", bad)
		}
		if err == nil {
			t.Errorf("Verify(%q) error = nil, want error", bad)
		}
	}
}
