// Package config 集中管理服务配置（环境变量 + .env）。
package config

import (
	"os"
	"strconv"
	"time"

	"github.com/joho/godotenv"
)

// Config 全部运行时配置。
type Config struct {
	// 服务
	AppEnv    string // dev | prod
	Port      string // 监听端口（默认 8090）
	Host      string // 监听地址（默认 127.0.0.1）
	SecretKey string // Session 签名密钥

	// 数据库
	DatabaseURL    string
	MigrateOnStart bool

	// 邮件 SMTP
	SMTPEnabled  bool
	SMTPHost     string
	SMTPPort     int
	SMTPUser     string
	SMTPPassword string
	SMTPFromName string
	ReceiverAll  string

	// CORS
	CORSOrigins []string

	// 存储
	AvatarDir string // 头像本地目录
	DataDir   string // 黑名单等数据目录
	MediaDir  string // 用户媒体（发帖图片）本地目录

	// SeaweedFS S3（新媒体）
	S3Enabled      bool
	S3Endpoint     string
	S3Region       string
	S3Bucket       string
	S3AccessKey    string
	S3SecretKey    string
	S3UsePathStyle bool

	// 媒体变体（S3 模式下上传时预生成 w480/w1280）
	MediaVariantsEnabled bool

	// 业务
	ImageFatherURL string
	PublicBaseURL  string // 站点对外地址（用于邮件链接）
	EasterEggPath  string // 彩蛋 JSON 文件路径

	// ALTCHA v2
	AltchaEnabled   bool
	AltchaHMACKey   string
	AltchaAlgorithm string
	AltchaCost      int
	AltchaExpires   time.Duration

	// 旧 APP 兼容层
	LegacyTokenTTL       time.Duration
	LegacyAppSunset      string
	LegacyTokenNotBefore time.Time

	// 下载页 GitHub Releases
	GitHubToken string
}

// Load 从 .env + 环境变量读取配置，缺省值对齐 legacy api/config.py。
// 同时尝试 server/.env（从仓库根目录运行时也能加载）。
func Load() *Config {
	_ = godotenv.Load(".env", "server/.env") // 不存在的文件与已导出的环境变量均被跳过

	cfg := &Config{
		AppEnv:    getEnv("APP_ENV", "prod"),
		Port:      getEnv("PORT", "8090"),
		Host:      getEnv("HOST", "127.0.0.1"),
		SecretKey: getEnv("SECRET_KEY", ""),

		DatabaseURL:    getEnv("DATABASE_URL", ""),
		MigrateOnStart: getEnvBool("MIGRATE_ON_START", true),

		SMTPEnabled:    getEnvBool("SMTP_ENABLED", true),
		SMTPHost:       getEnv("SMTP_HOST", "smtpdm.aliyun.com"),
		SMTPPort:       getEnvInt("SMTP_PORT", 465),
		SMTPUser:       getEnv("SMTP_USER", "maomi@email.yjlt.top"),
		SMTPPassword:   getEnv("SMTP_PASSWORD", ""),
		SMTPFromName:   getEnv("SMTP_FROM_NAME", "妖精论坛(二创)"),
		ReceiverAll:    getEnv("RECEIVERALL", ""),
		AvatarDir:      getEnv("AVATAR_DIR", "/var/yj-forum/avatar"),
		DataDir:        getEnv("DATA_DIR", "/var/yj-forum/data"),
		MediaDir:       getEnv("MEDIA_DIR", "/var/yj-forum/media"),
		S3Enabled:      getEnvBool("S3_ENABLED", false),
		S3Endpoint:     getEnv("S3_ENDPOINT", "http://127.0.0.1:8333"),
		S3Region:       getEnv("S3_REGION", "us-east-1"),
		S3Bucket:       getEnv("S3_BUCKET", "yj-forum"),
		S3AccessKey:    getEnv("S3_ACCESS_KEY", ""),
		S3SecretKey:    getEnv("S3_SECRET_KEY", ""),
		S3UsePathStyle: getEnvBool("S3_USE_PATH_STYLE", true),
		// 变体仅影响 S3 模式；默认开启，本地存储不受影响
		MediaVariantsEnabled: getEnvBool("MEDIA_VARIANTS_ENABLED", true),
		ImageFatherURL:       getEnv("IMAGE_FATHER_URL", "https://img.crazying-dev.top/text/one"),
		PublicBaseURL:        getEnv("PUBLIC_BASE_URL", "localhost:3000"),
		EasterEggPath:        getEnv("EASTER_EGG_PATH", "main/EasterEgg/1.json"),

		AltchaEnabled:   getEnvBool("ALTCHA_ENABLED", false),
		AltchaHMACKey:   getEnv("ALTCHA_HMAC_KEY", ""),
		AltchaAlgorithm: getEnv("ALTCHA_ALGORITHM", "PBKDF2/SHA-256"),
		AltchaCost:      getEnvInt("ALTCHA_COST", 5000),
		AltchaExpires:   time.Duration(getEnvInt("ALTCHA_EXPIRES_SECONDS", 600)) * time.Second,

		LegacyTokenTTL:       time.Duration(getEnvInt("LEGACY_TOKEN_TTL_HOURS", 168)) * time.Hour,
		LegacyAppSunset:      getEnv("LEGACY_APP_SUNSET", ""),
		LegacyTokenNotBefore: parseTimeEnv("LEGACY_TOKEN_NOT_BEFORE"),

		GitHubToken: getEnv("GITHUB_TOKEN", ""),
	}

	if cfg.ReceiverAll == "" {
		cfg.ReceiverAll = cfg.SMTPUser
	}

	origins := getEnv("CORS_ORIGINS", "")
	if origins != "" {
		cfg.CORSOrigins = splitComma(origins)
	}

	return cfg
}

func getEnv(key, def string) string {
	if v := os.Getenv(key); v != "" {
		return v
	}
	return def
}

func getEnvInt(key string, def int) int {
	if v := os.Getenv(key); v != "" {
		if n, err := strconv.Atoi(v); err == nil {
			return n
		}
	}
	return def
}

func getEnvBool(key string, def bool) bool {
	if v := os.Getenv(key); v != "" {
		if b, err := strconv.ParseBool(v); err == nil {
			return b
		}
	}
	return def
}

func parseTimeEnv(key string) time.Time {
	v := os.Getenv(key)
	if v == "" {
		return time.Time{}
	}
	t, err := time.Parse(time.RFC3339, v)
	if err != nil {
		return time.Time{}
	}
	return t
}

func splitComma(s string) []string {
	var out []string
	cur := ""
	for _, ch := range s {
		if ch == ',' {
			if cur != "" {
				out = append(out, cur)
			}
			cur = ""
		} else {
			cur += string(ch)
		}
	}
	if cur != "" {
		out = append(out, cur)
	}
	return out
}
