// Package altcha 封装 ALTCHA v2 挑战签发/校验与一次性 grant 令牌。
//
// 设计要点：
//   - fail-closed：启用后缺少 HMAC key、数据库不可用或校验异常都拒绝，不放行；
//   - 挑战一次性：校验通过后把 challenge id 写入 altcha_used（ON CONFLICT DO NOTHING），
//     并发重放只有一个请求能成功；
//   - grant：HMAC-SHA256 签名的短令牌，5 分钟内有效，供同一用户后续提交复用。
package altcha

import (
	"context"
	"crypto/hmac"
	"crypto/sha256"
	"encoding/base64"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"math/rand/v2"
	"strconv"
	"strings"
	"time"

	altchalib "github.com/altcha-org/altcha-lib-go/v2"

	"yj-forum/server/internal/database"
)

const (
	// DefaultAlgorithm ALTCHA 默认 KDF 算法。
	DefaultAlgorithm = "PBKDF2/SHA-256"
	// DefaultCost 默认 KDF 迭代次数。
	DefaultCost = 5000
	// DefaultExpires 挑战默认有效期（与 config 缺省一致）。
	DefaultExpires = 10 * time.Minute
	// GrantTTL grant 令牌有效期。
	GrantTTL = 5 * time.Minute

	maxPayloadLength = 64 << 10 // base64 载荷上限，防大 payload DoS
	grantVersion     = "v1"
)

var (
	// ErrDisabled ALTCHA 未启用。
	ErrDisabled = errors.New("altcha: disabled")
	// ErrNotConfigured 启用但缺少 HMAC key 或存储。
	ErrNotConfigured = errors.New("altcha: not configured")
	// ErrInvalidPayload 载荷格式错误。
	ErrInvalidPayload = errors.New("altcha: invalid payload")
	// ErrUnsupportedAlgorithm 不支持的 KDF 算法。
	ErrUnsupportedAlgorithm = errors.New("altcha: unsupported algorithm")
)

// Config 构造 Service 所需配置（通常来自 config.Config 的 Altcha* 字段）。
type Config struct {
	Enabled   bool
	HMACKey   string
	Algorithm string
	Cost      int
	Expires   time.Duration
}

// challengeStore 记录已消费的挑战 id；生产实现写 altcha_used 表。
type challengeStore interface {
	Consume(ctx context.Context, challengeID string, expiresAt time.Time) (bool, error)
}

type dbChallengeStore struct {
	db *database.DB
}

// Consume 原子占用挑战 id：首次写入返回 true，重复写入（重放）返回 false。
func (s *dbChallengeStore) Consume(ctx context.Context, challengeID string, expiresAt time.Time) (bool, error) {
	if s == nil || s.db == nil {
		return false, ErrNotConfigured
	}
	n, err := s.db.Exec(ctx,
		`INSERT INTO altcha_used (challenge_id, expires_at) VALUES ($1, $2)
		 ON CONFLICT (challenge_id) DO NOTHING`,
		challengeID, expiresAt)
	if err != nil {
		return false, fmt.Errorf("altcha: 记录已用挑战失败: %w", err)
	}
	return n == 1, nil
}

// Service ALTCHA v2 服务。零值不可用；请用 New 构造。
type Service struct {
	store     challengeStore
	enabled   bool
	hmacKey   string
	algorithm string
	cost      int
	expires   time.Duration

	// 测试注入点。
	now     func() time.Time
	randInt func(n int) int
}

// New 创建 ALTCHA 服务；db 可为 nil（此时校验会 fail-closed 拒绝）。
func New(db *database.DB, cfg Config) *Service {
	algorithm := strings.TrimSpace(cfg.Algorithm)
	if algorithm == "" {
		algorithm = DefaultAlgorithm
	}
	cost := cfg.Cost
	if cost <= 0 {
		cost = DefaultCost
	}
	expires := cfg.Expires
	if expires <= 0 {
		expires = DefaultExpires
	}
	s := &Service{
		enabled:   cfg.Enabled,
		hmacKey:   cfg.HMACKey,
		algorithm: algorithm,
		cost:      cost,
		expires:   expires,
		now:       time.Now,
		randInt:   rand.IntN,
	}
	if db != nil {
		s.store = &dbChallengeStore{db: db}
	}
	return s
}

// Enabled 是否启用 ALTCHA。注意：启用但配置无效时仍返回 true，
// 让调用方继续要求校验并由 Challenge/Verify 返回错误（fail-closed）。
func (s *Service) Enabled() bool {
	return s != nil && s.enabled
}

// Algorithm 当前 KDF 算法（用于 /captcha/config）。
func (s *Service) Algorithm() string {
	if s == nil || s.algorithm == "" {
		return DefaultAlgorithm
	}
	return s.algorithm
}

// Cost 当前 KDF 迭代次数（用于 /captcha/config）。
func (s *Service) Cost() int {
	if s == nil || s.cost <= 0 {
		return DefaultCost
	}
	return s.cost
}

func (s *Service) configured() bool {
	return s != nil && strings.TrimSpace(s.hmacKey) != ""
}

// Challenge 签发一个 ALTCHA v2 挑战（确定性 counter 模式，客户端从 0 扫描到 counter）。
func (s *Service) Challenge(ctx context.Context) (altchalib.Challenge, error) {
	_ = ctx
	if !s.Enabled() {
		return altchalib.Challenge{}, ErrDisabled
	}
	if !s.configured() {
		return altchalib.Challenge{}, ErrNotConfigured
	}
	deriveKey, err := deriveKeyFor(s.algorithm)
	if err != nil {
		return altchalib.Challenge{}, err
	}

	// counter 取 [cost, 2*cost)，让求解成本约为 cost 次 KDF。
	counter := s.cost + s.randInt(s.cost)
	expiresAt := s.now().Add(s.expires)
	challenge, err := altchalib.CreateChallenge(altchalib.CreateChallengeOptions{
		Algorithm:              s.algorithm,
		Cost:                   s.cost,
		Counter:                &counter,
		DeriveKey:              deriveKey,
		ExpiresAt:              &expiresAt,
		KeyLength:              32,
		HMACSignatureSecret:    s.hmacKey,
		HMACKeySignatureSecret: s.hmacKey,
	})
	if err != nil {
		return altchalib.Challenge{}, fmt.Errorf("altcha: 创建挑战失败: %w", err)
	}
	return challenge, nil
}

// Verify 校验 base64 编码的 ALTCHA payload；成功即消费该挑战（一次性）。
// 返回 (false, nil) 表示校验不通过/已重放；返回 error 表示配置或存储异常，调用方必须拒绝。
func (s *Service) Verify(ctx context.Context, altchaPayload string) (bool, error) {
	if !s.Enabled() {
		return false, ErrDisabled
	}
	if !s.configured() {
		return false, ErrNotConfigured
	}

	raw, err := decodePayload(altchaPayload)
	if err != nil {
		return false, err
	}
	var payload altchalib.Payload
	if err := json.Unmarshal(raw, &payload); err != nil {
		return false, ErrInvalidPayload
	}

	challengeID := strings.TrimSpace(payload.Challenge.Parameters.Nonce)
	if challengeID == "" || len(challengeID) > 128 {
		return false, ErrInvalidPayload
	}

	deriveKey, err := deriveKeyFor(payload.Challenge.Parameters.Algorithm)
	if err != nil {
		return false, err
	}
	result, err := altchalib.VerifySolution(altchalib.VerifySolutionOptions{
		Challenge:              payload.Challenge,
		Solution:               payload.Solution,
		DeriveKey:              deriveKey,
		HMACSignatureSecret:    s.hmacKey,
		HMACKeySignatureSecret: s.hmacKey,
	})
	if err != nil {
		return false, fmt.Errorf("altcha: 校验失败: %w", err)
	}
	if result.Expired || !result.Verified {
		return false, nil
	}
	if s.store == nil {
		return false, ErrNotConfigured
	}

	expiresAt := s.now().Add(s.expires)
	if payload.Challenge.Parameters.ExpiresAt > 0 {
		expiresAt = time.Unix(payload.Challenge.Parameters.ExpiresAt, 0)
	}
	return s.store.Consume(ctx, challengeID, expiresAt)
}

// Grant 签发 5 分钟有效的 HMAC-SHA256 grant 令牌。
func (s *Service) Grant(ip ...string) (string, error) {
	if !s.Enabled() {
		return "", ErrDisabled
	}
	if !s.configured() {
		return "", ErrNotConfigured
	}
	bind := ""
	if len(ip) > 0 {
		bind = strings.TrimSpace(ip[0])
	}
	sum := sha256.Sum256([]byte(bind))
	expiresAt := s.now().Add(GrantTTL).Unix()
	payload := grantVersion + ":" + strconv.FormatInt(expiresAt, 10) + ":" + hex.EncodeToString(sum[:8])
	return signToken(payload, s.hmacKey), nil
}

// VerifyGrant 校验 grant 令牌的签名与有效期。
func (s *Service) VerifyGrant(token string, ip ...string) bool {
	if !s.Enabled() || !s.configured() {
		return false
	}
	parts := strings.Split(strings.TrimSpace(token), ".")
	if len(parts) != 2 || parts[0] == "" || parts[1] == "" {
		return false
	}

	mac := hmac.New(sha256.New, []byte(s.hmacKey))
	mac.Write([]byte(parts[0]))
	signature, err := base64.RawURLEncoding.DecodeString(parts[1])
	if err != nil || !hmac.Equal(signature, mac.Sum(nil)) {
		return false
	}

	raw, err := base64.RawURLEncoding.DecodeString(parts[0])
	if err != nil {
		return false
	}
	payload := string(raw)
	partsPayload := strings.Split(payload, ":")
	if len(partsPayload) != 3 || partsPayload[0] != grantVersion {
		return false
	}
	expiresAt, err := strconv.ParseInt(partsPayload[1], 10, 64)
	if err != nil {
		return false
	}
	bind := ""
	if len(ip) > 0 {
		bind = strings.TrimSpace(ip[0])
	}
	sum := sha256.Sum256([]byte(bind))
	if !hmac.Equal([]byte(partsPayload[2]), []byte(hex.EncodeToString(sum[:8]))) {
		return false
	}
	return s.now().Before(time.Unix(expiresAt, 0))
}

func signToken(payload, key string) string {
	body := base64.RawURLEncoding.EncodeToString([]byte(payload))
	mac := hmac.New(sha256.New, []byte(key))
	mac.Write([]byte(body))
	return body + "." + base64.RawURLEncoding.EncodeToString(mac.Sum(nil))
}

// decodePayload 兼容标准/URL-safe、带/不带 padding 的 base64。
func decodePayload(payload string) ([]byte, error) {
	payload = strings.TrimSpace(payload)
	if payload == "" || len(payload) > maxPayloadLength {
		return nil, ErrInvalidPayload
	}
	encodings := []*base64.Encoding{
		base64.StdEncoding,
		base64.RawStdEncoding,
		base64.URLEncoding,
		base64.RawURLEncoding,
	}
	for _, enc := range encodings {
		if raw, err := enc.DecodeString(payload); err == nil {
			return raw, nil
		}
	}
	return nil, ErrInvalidPayload
}

// deriveKeyFor 按挑战里的算法选择库提供的 KDF 实现。
func deriveKeyFor(algorithm string) (altchalib.DeriveKeyFunc, error) {
	upper := strings.ToUpper(strings.TrimSpace(algorithm))
	switch {
	case strings.HasPrefix(upper, "PBKDF2/"):
		return altchalib.DeriveKeyPBKDF2(), nil
	case strings.HasPrefix(upper, "SHA-"):
		return altchalib.DeriveKeySHA(), nil
	case strings.HasPrefix(upper, "SCRYPT"):
		return altchalib.DeriveKeyScrypt(), nil
	case strings.HasPrefix(upper, "ARGON2ID"):
		return altchalib.DeriveKeyArgon2id(), nil
	default:
		return nil, fmt.Errorf("%w: %s", ErrUnsupportedAlgorithm, algorithm)
	}
}
