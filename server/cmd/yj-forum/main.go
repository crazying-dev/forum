// yj-forum-server 妖精论坛 v2 后端服务
package main

import (
	"context"
	"errors"
	"log"
	"net/http"
	"os"
	"os/signal"
	"path/filepath"
	"strings"
	"syscall"
	"time"

	"github.com/gin-gonic/gin"

	"yj-forum/server/internal/auth"
	"yj-forum/server/internal/config"
	"yj-forum/server/internal/database"
	"yj-forum/server/internal/email"
	"yj-forum/server/internal/handler"
)

func main() {
	cfg := config.Load()

	if cfg.SecretKey == "" {
		log.Println("[WARN] SECRET_KEY 未设置，使用开发默认值")
		cfg.SecretKey = "dev-secret-key"
	}

	// 1. 数据库
	ctx := context.Background()
	db, err := database.New(ctx, cfg.DatabaseURL)
	if err != nil {
		log.Fatalf("[FATAL] 数据库初始化失败: %v", err)
	}
	defer db.Close()

	// 2. 迁移（golang-migrate，嵌入二进制，无工作目录依赖）；失败即退出（fail-fast），
	// 避免缺失新列/新表时无守卫引用打挂核心读路径
	if err := database.Migrate(cfg.DatabaseURL); err != nil {
		log.Fatalf("[FATAL] 数据库迁移失败，服务退出: %v", err)
	}
	log.Println("[DB] 迁移完成")

	// 3. 会话/邮件
	sessions := &auth.SessionManager{DB: db}
	mailer := email.New(cfg.SMTPEnabled, cfg.SMTPHost, cfg.SMTPPort, cfg.SMTPUser, cfg.SMTPPassword, cfg.SMTPFromName, cfg.ReceiverAll)

	// 4. 路由（返回帖子处理器，供定时发布任务复用 DB/缓存）
	gin.SetMode(gin.ReleaseMode)
	r := gin.New()
	postsH := handler.Register(r, cfg, db, sessions, mailer)

	// 5. 后台任务（10 分钟：会话/验证码；1 小时：过期媒体文件；1 分钟：定时帖到点补发通知）
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
			case <-mediaTicker.C:
				cleanDeletedMediaFiles(ctx, db, cfg.MediaDir)
			case <-publishTicker.C:
				postsH.ProcessScheduledPublishes(ctx)
			}
		}
	}()

	// 6. HTTP 服务
	srv := &http.Server{
		Addr:    cfg.Host + ":" + cfg.Port,
		Handler: r,
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
	shutdownCtx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()
	_ = srv.Shutdown(shutdownCtx)
}

// cleanDeletedMediaFiles 清理已删除（status=0）且超过 7 天的媒体物理文件；行记录保留，文件已不存在则忽略。
func cleanDeletedMediaFiles(ctx context.Context, db *database.DB, mediaDir string) {
	assets, err := db.ListExpiredMediaAssets(ctx, 7)
	if err != nil {
		log.Printf("[MEDIA] 过期媒体查询失败: %v", err)
		return
	}
	removed := 0
	for _, a := range assets {
		// 路径穿越防护（防御性，文件名本由服务端生成）
		if a.FileName == "" || strings.Contains(a.FileName, "..") ||
			strings.Contains(a.FileName, "/") || strings.Contains(a.FileName, "\\") {
			continue
		}
		if err := os.Remove(filepath.Join(mediaDir, a.FileName)); err == nil {
			removed++
		}
	}
	if removed > 0 {
		log.Printf("[MEDIA] 已清理 %d 个过期媒体文件", removed)
	}
}
