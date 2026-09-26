// Package config 集中管理服务配置（环境变量 + .env）。
package config

import (
	"os"
	"strconv"

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
	DatabaseURL string

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

	// 业务
	ImageFatherURL string
	PublicBaseURL  string // 站点对外地址（用于邮件链接）
	EasterEggPath  string // 彩蛋 JSON 文件路径
}

// Load 从 .env + 环境变量读取配置，缺省值对齐 legacy api/config.py。
// 同时尝试 server/.env（从仓库根目录运行时也能加载）。
func Load() *Config {
	_ = godotenv.Load(".env", "server/.env") // 不存在的文件与已导出的环境变量均被跳过

	cfg := &Config{
		AppEnv:    getEnv("APP_ENV", "dev"),
		Port:      getEnv("PORT", "8090"),
		Host:      getEnv("HOST", "127.0.0.1"),
		SecretKey: getEnv("SECRET_KEY", ""),

		DatabaseURL: getEnv("DATABASE_URL", ""),

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
		ImageFatherURL: getEnv("IMAGE_FATHER_URL", "https://img.crazying-dev.top/text/one"),
		PublicBaseURL:  getEnv("PUBLIC_BASE_URL", "localhost:3000"),
		EasterEggPath:  getEnv("EASTER_EGG_PATH", "main/EasterEgg/1.json"),
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
