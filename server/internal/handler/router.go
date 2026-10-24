package handler

import (
	"context"
	"net/http"
	"time"

	"github.com/gin-gonic/gin"

	"yj-forum/server/internal/altcha"
	"yj-forum/server/internal/auth"
	"yj-forum/server/internal/config"
	"yj-forum/server/internal/database"
	"yj-forum/server/internal/email"
	"yj-forum/server/internal/media"
	"yj-forum/server/internal/middleware"
	"yj-forum/server/internal/releases"
	"yj-forum/server/internal/sse"
)

type apiHandlers struct {
	authH                  *AuthHandler
	postsH                 *PostsHandler
	miscH                  *MiscHandler
	accountH               *AccountHandler
	siteH                  *SiteHandler
	guildsH                *GuildsHandler
	mediaH                 *MediaHandler
	embedsH                *EmbedsHandler
	guidesH                *GuidesHandler
	captchaH               *CaptchaHandler
	siteFeatureH           *SiteFeatureHandlers
	messagesH              *MessageHandler
	worldH                 *WorldHandler
	emailChangeVerifyLimit gin.HandlerFunc
}

// Register 注册全部路由：/ov2/api 为 canonical；/api/v1 为新 shape 别名（一个版本周期）。
// 旧 APP 兼容层 /api/* 由 legacy.RegisterRoutes 单独挂载（Step 6）。
func Register(r *gin.Engine, cfg *config.Config, db *database.DB, sessions *auth.SessionManager, mailer *email.Sender, mediaSvc *media.Service, cacheSet *CacheSet) *PostsHandler {
	r.Use(middleware.Logger())
	r.Use(middleware.SecurityHeaders())
	r.Use(middleware.CORS(cfg.CORSOrigins, cfg.AppEnv != "prod"))
	r.Use(middleware.Gzip())
	r.Use(middleware.CSRF(cfg.CORSOrigins))

	if cacheSet == nil {
		cacheSet = NewCacheSet()
	}

	// 根路径健康检查：DB 与 S3（启用时）各限时 3s 探测，全部正常 200，否则 503。
	r.GET("/healthz", func(c *gin.Context) {
		resp := gin.H{"ok": true, "service": "yj-forum", "db": "ok", "s3": "disabled"}
		code := http.StatusOK
		if db == nil || db.Pool == nil {
			resp["ok"], resp["db"] = false, "error"
			code = http.StatusServiceUnavailable
		} else {
			dbCtx, dbCancel := context.WithTimeout(c.Request.Context(), 3*time.Second)
			err := db.Pool.Ping(dbCtx)
			dbCancel()
			if err != nil {
				resp["ok"], resp["db"] = false, "error"
				code = http.StatusServiceUnavailable
			}
		}
		if mediaSvc != nil && mediaSvc.S3 != nil {
			s3Ctx, s3Cancel := context.WithTimeout(c.Request.Context(), 3*time.Second)
			err := mediaSvc.S3.Ping(s3Ctx)
			s3Cancel()
			if err != nil {
				resp["ok"], resp["s3"] = false, "error"
				code = http.StatusServiceUnavailable
			} else {
				resp["s3"] = "ok"
			}
		}
		c.JSON(code, resp)
	})
	altchaSvc := altcha.New(db, altcha.Config{
		Enabled: cfg.AltchaEnabled, HMACKey: cfg.AltchaHMACKey,
		Algorithm: cfg.AltchaAlgorithm, Cost: cfg.AltchaCost, Expires: cfg.AltchaExpires,
	})
	authH := &AuthHandler{DB: db, Cfg: cfg, Sessions: sessions, Mailer: mailer, Altcha: altchaSvc}
	postsH := &PostsHandler{DB: db, Cfg: cfg, Cache: cacheSet, Mailer: mailer, Sessions: sessions, Media: mediaSvc, Altcha: altchaSvc}
	miscH := &MiscHandler{DB: db, Cfg: cfg, Mailer: mailer, Sessions: sessions, Altcha: altchaSvc}
	accountH := &AccountHandler{DB: db, Cfg: cfg, Mailer: mailer, Sessions: sessions, Cache: cacheSet}
	siteH := &SiteHandler{DB: db}
	guildsH := &GuildsHandler{DB: db, Cache: cacheSet, Sessions: sessions}
	mediaH := &MediaHandler{DB: db, Cfg: cfg, Media: mediaSvc, Sessions: sessions}
	embedsH := &EmbedsHandler{DB: db}
	guidesH := &GuidesHandler{DB: db}

	hub := sse.NewHub()
	SetMessageHub(hub)
	messagesH := &MessageHandler{DB: db, Sessions: sessions}
	worldH := &WorldHandler{DB: db, Cfg: cfg, Hub: hub, Sessions: sessions}
	captchaH := NewCaptchaHandler(altchaSvc)
	siteFeatureH := NewSiteFeatureHandlers(db, releases.NewService(cfg.GitHubToken))

	h := apiHandlers{
		authH: authH, postsH: postsH, miscH: miscH, accountH: accountH,
		siteH: siteH, guildsH: guildsH, mediaH: mediaH, embedsH: embedsH, guidesH: guidesH,
		captchaH: captchaH, siteFeatureH: siteFeatureH, messagesH: messagesH, worldH: worldH,
		// 邮箱换绑两步验证共用同一 IP 频控桶（两侧使用同一实例才能共享计数）
		emailChangeVerifyLimit: middleware.RateLimit("email_change_verify", 15, 5*time.Minute),
	}

	apiV2 := r.Group("/ov2/api")
	registerAPIRoutes(apiV2, h)

	apiV1 := r.Group("/api/v1")
	apiV1.Use(func(c *gin.Context) {
		c.Header("Deprecation", "true")
		c.Next()
	})
	registerAPIRoutes(apiV1, h)

	// 旧 APP 兼容层：/api/*（不含 /api/v1），独立 handler，显式跳过 CSRF
	RegisterLegacyRoutes(r, cfg, db, sessions, mailer)

	return postsH
}

func registerAPIRoutes(api *gin.RouterGroup, h apiHandlers) {
	authH, postsH, miscH, accountH := h.authH, h.postsH, h.miscH, h.accountH
	siteH, guildsH, mediaH, embedsH, guidesH := h.siteH, h.guildsH, h.mediaH, h.embedsH, h.guidesH

	api.GET("/healthz", func(c *gin.Context) {
		c.JSON(200, gin.H{"ok": true, "service": "yj-forum"})
	})

	// ---- 认证 ----
	api.POST("/auth/register", authH.Register)
	api.POST("/auth/login", authH.Login)
	api.POST("/auth/logout", authH.Logout)
	api.GET("/auth/oauth/callback", authH.HandleOAuth) // 兼容第三方登录（TheDoorOfBings）

	// ---- 验证码/邮件 ----
	api.POST("/auth/register/code", miscH.SendRegisterCode)
	api.POST("/auth/password/reset/link", middleware.RateLimit("reset_link", 10, time.Hour), miscH.SendResetLink)
	api.GET("/auth/password/reset/validate", middleware.RateLimit("reset_validate", 30, 5*time.Minute), miscH.ValidateResetToken)
	api.POST("/auth/password/reset/confirm", miscH.ResetPasswordByToken)
	api.GET("/auth/verify-token", miscH.VerifyToken)

	// ---- 用户 ----
	api.GET("/users/me", authH.Me)
	api.PATCH("/users/me", authH.AuthRequired(), authH.UpdateMe)
	api.POST("/users/me/sign-in", authH.AuthRequired(), authH.SignIn)
	api.GET("/users/me/replies", authH.AuthRequired(), authH.MyReplies)
	api.POST("/users/me/verify-email", authH.AuthRequired(), miscH.SendVerifyEmailCode)
	api.POST("/users/me/verify-email/confirm", middleware.RateLimit("verify_email", 10, 5*time.Minute), authH.AuthRequired(), miscH.VerifyCodeEmail)
	api.POST("/users/me/delete", middleware.RateLimit("account_delete", 5, 300*time.Second), authH.AuthRequired(), accountH.DeleteAccount)
	api.POST("/users/me/email-change/code", middleware.RateLimit("email_change_code", 10, 10*time.Minute), authH.AuthRequired(), accountH.SendEmailChangeOldCode)
	api.POST("/users/me/email-change/verify-old", h.emailChangeVerifyLimit, authH.AuthRequired(), accountH.VerifyEmailChangeOld)
	api.POST("/users/me/email-change/new-code", middleware.RateLimit("email_change_new", 10, 10*time.Minute), authH.AuthRequired(), accountH.SendEmailChangeNewCode)
	api.POST("/users/me/email-change/confirm", h.emailChangeVerifyLimit, authH.AuthRequired(), accountH.ConfirmEmailChange)
	api.GET("/users/:id", authH.UserProfile)
	api.GET("/users/:id/posts", authH.UserPosts)
	api.GET("/users/:id/comments", authH.UserComments)
	api.GET("/users/:id/favorites", authH.UserFavorites)
	api.POST("/users/:id/follow", authH.AuthRequired(), authH.ToggleFollow)
	api.GET("/users/:id/following", authH.Following)
	api.GET("/users/:id/followers", authH.Followers)
	api.GET("/users/:id/mutual", authH.Mutual)

	// ---- 帖子 ----
	api.GET("/posts", postsH.List)
	api.GET("/posts/random", postsH.Random)
	api.GET("/posts/picker-defaults", postsH.AuthRequired(), postsH.PickerDefaults)
	api.GET("/posts/:id", postsH.Detail)
	api.POST("/posts", postsH.AuthRequired(), postsH.Create)
	api.POST("/posts/:id/like", postsH.AuthRequired(), postsH.Like)
	api.POST("/posts/:id/favorite", postsH.AuthRequired(), postsH.Favorite)
	api.POST("/posts/:id/delete", postsH.AuthRequired(), postsH.Delete)
	api.POST("/posts/:id/report", postsH.AuthRequired(), postsH.Report)

	// ---- 评论 ----
	api.GET("/posts/:id/comments", postsH.Comments)
	api.POST("/posts/:id/comments", postsH.AuthRequired(), postsH.CreateComment)
	api.DELETE("/comments/:id", postsH.AuthRequired(), postsH.DeleteComment)
	api.POST("/comments/:id/like", postsH.AuthRequired(), postsH.LikeComment)

	// ---- 会馆 / 信息流 ----
	api.GET("/guilds", guildsH.List)
	api.GET("/guilds/:slug", guildsH.Detail)
	api.GET("/guilds/:slug/feed", guildsH.Feed)
	api.GET("/guilds/:slug/members", guildsH.Members)
	api.GET("/guilds/:slug/leader", guildsH.LeaderPage)
	api.GET("/guilds/:slug/intro", guildsH.IntroPage)
	api.POST("/guilds/:slug/join", authH.AuthRequired(), guildsH.Join)
	api.POST("/guilds/:slug/join/cancel", authH.AuthRequired(), guildsH.CancelJoin)
	api.POST("/guilds/:slug/leave", authH.AuthRequired(), guildsH.Leave)
	api.GET("/feed", guildsH.GlobalFeed)
	api.GET("/articles/search", guildsH.SearchArticles)
	api.GET("/articles/:id", guildsH.Article)

	// ---- 搜索 ----
	api.GET("/search", postsH.Search)

	// ---- 指南（公开读取）----
	api.GET("/guides", guidesH.List)
	api.GET("/guides/:id", guidesH.Detail)

	// ---- 站点配置（公开）----
	api.GET("/site/config", siteH.SiteConfig)

	// ---- 引用卡片 / 媒体 ----
	api.GET("/embeds", embedsH.List)
	api.POST("/media/images", middleware.RateLimit("media_image", 30, 600*time.Second), authH.AuthRequired(), mediaH.UploadImage)
	api.GET("/media/:id", authH.OptionalAuth(), mediaH.ServeImage)
	// HEAD 供探针/爬虫与 nginx 缓存校验使用（gin 不会自动为 GET 注册 HEAD）。
	api.HEAD("/media/:id", authH.OptionalAuth(), mediaH.ServeImage)

	// ---- 投票 / 举报 / 杂项 ----
	api.POST("/votes/version", miscH.VoteVersion)
	api.GET("/votes/version/stats", miscH.VoteVersionStats)
	// 反馈接口限流：提交 20 次/小时，公开读取 120 次/分钟（按 IP 分桶）
	api.POST("/reports/bug", middleware.RateLimit("report_bug_create", 20, time.Hour), miscH.ReportBug)
	api.GET("/reports/bug", middleware.RateLimit("report_bug_list", 120, time.Minute), miscH.ListBugReports)
	api.GET("/reports/bug/stats", middleware.RateLimit("report_bug_stats", 120, time.Minute), miscH.BugReportStats)
	api.GET("/reports/bug/:id", middleware.RateLimit("report_bug_detail", 120, time.Minute), miscH.BugReportDetail)
	api.GET("/easter-egg", miscH.EasterEgg)

	api.POST("/users/me/avatar", authH.AuthRequired(), postsH.UploadAvatar)
	api.GET("/avatar/:filename", postsH.ServeAvatar)

	// ---- 新增模块（Batch 2）----
	RegisterCaptchaRoutes(api, h.captchaH)
	RegisterSiteFeatureRoutes(api, h.siteFeatureH)
	RegisterMessageRoutes(api, h.messagesH)
	RegisterWorldRoutes(api, h.worldH)
}
