// yj-forum-server 妖精论坛 v2 后端服务
package main

import (
	"context"
	"errors"
	"log"
	"net/http"
	"os"
	"os/signal"
	"syscall"
	"time"

	"github.com/gin-gonic/gin"

	"yj-forum/server/internal/auth"
	"yj-forum/server/internal/config"
	"yj-forum/server/internal/database"
	"yj-forum/server/internal/email"
	"yj-forum/server/internal/handler"
	"yj-forum/server/internal/media"
	"yj-forum/server/internal/queue"
	"yj-forum/server/internal/storage"
	"yj-forum/server/internal/world"
)

func main() {
	cfg := config.Load()

	if cfg.SecretKey == "" {
		if cfg.AppEnv == "prod" {
			log.Fatalf("[FATAL] 生产环境必须设置 SECRET_KEY（建议 32+ 字节随机值）")
		}
		log.Println("[WARN] SECRET_KEY 未设置，使用开发默认值")
		cfg.SecretKey = "dev-secret-key"
	}
	if cfg.AppEnv == "prod" && (cfg.SecretKey == "dev-secret-key" || cfg.SecretKey == "TestKeyFor1" || len(cfg.SecretKey) < 32) {
		log.Fatalf("[FATAL] 生产环境 SECRET_KEY 过弱（需 32+ 字节且不能使用默认值）")
	}

	// 1. 数据库
	ctx := context.Background()
	db, err := database.New(ctx, cfg.DatabaseURL)
	if err != nil {
		log.Fatalf("[FATAL] 数据库初始化失败: %v", err)
	}
	defer db.Close()

	// 2. 迁移（golang-migrate，嵌入二进制，无工作目录依赖）；失败即退出（fail-fast）。
	// 生产建议 MIGRATE_ON_START=false，由一次性迁移 job 执行（见 docs/migration-baseline.md）。
	if cfg.MigrateOnStart {
		if err := database.Migrate(cfg.DatabaseURL); err != nil {
			log.Fatalf("[FATAL] 数据库迁移失败，服务退出: %v", err)
		}
		log.Println("[DB] 迁移完成")
	} else {
		log.Println("[DB] MIGRATE_ON_START=false，跳过启动迁移")
	}

	// 3. 会话/邮件
	sessions := &auth.SessionManager{DB: db}
	mailer := email.New(cfg.SMTPEnabled, cfg.SMTPHost, cfg.SMTPPort, cfg.SMTPUser, cfg.SMTPPassword, cfg.SMTPFromName, cfg.ReceiverAll)

	// 3.1 媒体存储：S3 可用时新数据写 SeaweedFS，否则回退本地 MEDIA_DIR（旧资产永远可读）
	var s3Provider *storage.S3Provider
	if cfg.S3Enabled {
		var s3Err error
		s3Provider, s3Err = storage.NewS3(ctx, storage.S3Config{
			Endpoint: cfg.S3Endpoint, Region: cfg.S3Region, Bucket: cfg.S3Bucket,
			AccessKey: cfg.S3AccessKey, SecretKey: cfg.S3SecretKey, UsePathStyle: cfg.S3UsePathStyle,
		})
		if s3Err != nil {
			log.Fatalf("[FATAL] S3 初始化失败: %v", s3Err)
		}
		log.Printf("[MEDIA] S3 已启用: %s bucket=%s", cfg.S3Endpoint, cfg.S3Bucket)
	} else {
		log.Println("[MEDIA] S3 未启用，新媒体落本地 MEDIA_DIR")
	}
	mediaSvc := media.NewService(db, s3Provider, cfg.MediaDir, cfg.S3Bucket)

	// 4. 路由（返回帖子处理器，供定时发布任务复用 DB/缓存）
	gin.SetMode(gin.ReleaseMode)
	r := gin.New()
	// 仅信任本机反代（dev 的 Next 重写 / prod 的 Nginx）：避免客户端伪造 X-Forwarded-For 绕过 IP 限流
	if err := r.SetTrustedProxies([]string{"127.0.0.1", "::1"}); err != nil {
		log.Printf("[SERVER] 设置可信代理失败: %v", err)
	}
	cacheSet := handler.NewCacheSet()
	postsH := handler.Register(r, cfg, db, sessions, mailer, mediaSvc, cacheSet)
	hub := handler.ActiveMessageHub()

	// 5. 后台任务（10 分钟：会话/验证码；1 小时：过期媒体文件；1 分钟：定时帖到点补发通知）
	workerCtx, workerCancel := context.WithCancel(context.Background())
	defer workerCancel()
	go queue.Start(workerCtx, db, mailer, cacheSet)
	go world.StartPoller(workerCtx, db, hub)
	go world.StartCleanup(workerCtx, db)

	go func() {
		cleanTicker := time.NewTicker(10 * time.Minute)
		defer cleanTicker.Stop()
		mediaTicker := time.NewTicker(1 * time.Hour)
		defer mediaTicker.Stop()
		publishTicker := time.NewTicker(1 * time.Minute)
		defer publishTicker.Stop()
		for {
			select {
			case <-cleanTicker.C:
				sessions.Cleanup(ctx)
				_ = db.CleanExpiredVerifyCodes(ctx)
				if err := db.CleanExpiredVerifyTokens(ctx); err != nil {
					log.Printf("[DB] 清理过期验证 token 失败: %v", err)
				}
				if err := db.CleanOldAccountActionLimits(ctx); err != nil {
					log.Printf("[DB] 清理账号操作限流记录失败: %v", err)
				}
				if err := db.CleanExpiredAltchaUsed(ctx); err != nil {
					log.Printf("[DB] 清理 ALTCHA 记录失败: %v", err)
				}
			case <-mediaTicker.C:
				cleanDeletedMediaFiles(ctx, db, mediaSvc)
			case <-publishTicker.C:
				postsH.ProcessScheduledPublishes(ctx)
			}
		}
	}()

	// 6. HTTP 服务
	srv := &http.Server{
		Addr:              cfg.Host + ":" + cfg.Port,
		Handler:           r,
		ReadHeaderTimeout: 5 * time.Second,
		IdleTimeout:       60 * time.Second,
		// WriteTimeout 保持 0：SSE 需要长连接；普通接口由 handler 自身超时/限流保护
	}

	go func() {
		log.Printf("[SERVER] 妖精论坛 v2 后端启动: http://%s:%s", cfg.Host, cfg.Port)
		if err := srv.ListenAndServe(); err != nil && !errors.Is(err, http.ErrServerClosed) {
			log.Fatalf("[FATAL] 服务启动失败: %v", err)
		}
	}()

	// 优雅退出
	quit := make(chan os.Signal, 1)
	signal.Notify(quit, syscall.SIGINT, syscall.SIGTERM)
	<-quit
	log.Println("[SERVER] 正在关闭...")
	workerCancel()
	shutdownCtx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()
	_ = srv.Shutdown(shutdownCtx)
}

// cleanDeletedMediaFiles 清理已删除（status=0）且超过 7 天的媒体对象；
// is_legacy / 有活跃引用的资产永不删除；行记录保留。
func cleanDeletedMediaFiles(ctx context.Context, db *database.DB, mediaSvc *media.Service) {
	assets, err := db.ListExpiredMediaAssets(ctx, 7)
	if err != nil {
		log.Printf("[MEDIA] 过期媒体查询失败: %v", err)
		return
	}
	removed := 0
	for i := range assets {
		a := &assets[i]
		if a.IsLegacy {
			continue
		}
		if err := mediaSvc.Delete(ctx, a); err == nil {
			removed++
		}
	}
	if removed > 0 {
		log.Printf("[MEDIA] 已清理 %d 个过期媒体对象", removed)
	}
}
