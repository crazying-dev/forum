package handler

import (
	"github.com/gin-gonic/gin"

	"yj-forum/server/internal/auth"
	"yj-forum/server/internal/config"
	"yj-forum/server/internal/database"
	"yj-forum/server/internal/email"
	"yj-forum/server/internal/middleware"
)

// Register 注册全部路由（RESTful /api/v1）。
func Register(r *gin.Engine, cfg *config.Config, db *database.DB, sessions *auth.SessionManager, mailer *email.Sender) {
	r.Use(middleware.Logger())
	r.Use(middleware.SecurityHeaders())
	r.Use(middleware.CORS(cfg.CORSOrigins))
	r.Use(middleware.Gzip())
	r.Use(middleware.CSRF(cfg.CORSOrigins))

	authH := &AuthHandler{DB: db, Cfg: cfg, Sessions: sessions, Mailer: mailer}
	cacheSet := NewCacheSet()
	postsH := &PostsHandler{DB: db, Cfg: cfg, Cache: cacheSet, Mailer: mailer, Sessions: sessions}
	miscH := &MiscHandler{DB: db, Cfg: cfg, Mailer: mailer, Sessions: sessions}
	guildsH := &GuildsHandler{DB: db, Cache: cacheSet, Sessions: sessions}

	api := r.Group("/api/v1")

	// ---- 认证 ----
	api.POST("/auth/register", authH.Register)
	api.POST("/auth/login", authH.Login)
	api.POST("/auth/logout", authH.Logout)
	api.GET("/auth/oauth/callback", authH.HandleOAuth) // 兼容第三方登录（TheDoorOfBings）

	// ---- 验证码/邮件 ----
	api.POST("/auth/register/code", miscH.SendRegisterCode)
	api.POST("/auth/password/reset/code", miscH.SendResetPasswordCode)
	api.POST("/auth/password/reset", miscH.ResetPasswordByCode)
	api.GET("/auth/verify-token", miscH.VerifyToken)

	// ---- 用户 ----
	api.GET("/users/me", authH.Me)
	api.PATCH("/users/me", authH.AuthRequired(), authH.UpdateMe)
	api.GET("/users/me/replies", authH.AuthRequired(), authH.MyReplies)
	api.POST("/users/me/verify-email", authH.AuthRequired(), miscH.SendVerifyEmailCode)
	api.POST("/users/me/verify-email/confirm", authH.AuthRequired(), miscH.VerifyCodeEmail)
	api.GET("/users/:id", authH.UserProfile)
	api.GET("/users/:id/posts", authH.UserPosts)
	api.GET("/users/:id/comments", authH.UserComments)
	api.GET("/users/:id/favorites", authH.UserFavorites)
	api.POST("/users/:id/follow", authH.AuthRequired(), authH.ToggleFollow)
	api.GET("/users/:id/following", authH.Following)
	api.GET("/users/:id/followers", authH.Followers)

	// ---- 帖子 ----
	api.GET("/posts", postsH.List)
	api.GET("/posts/random", postsH.Random)
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
	api.POST("/guilds/:slug/join", authH.AuthRequired(), guildsH.Join)
	api.POST("/guilds/:slug/join/cancel", authH.AuthRequired(), guildsH.CancelJoin)
	api.POST("/guilds/:slug/leave", authH.AuthRequired(), guildsH.Leave)
	api.GET("/feed", guildsH.GlobalFeed)
	api.GET("/articles/:id", guildsH.Article)

	// ---- 搜索 ----
	api.GET("/search", postsH.Search)

	// ---- 投票 / 举报 / 杂项 ----
	api.POST("/votes/version", miscH.VoteVersion)
	api.GET("/votes/version/stats", miscH.VoteVersionStats)
	api.POST("/reports/bug", miscH.ReportBug)
	api.GET("/easter-egg", miscH.EasterEgg)

	api.POST("/users/me/avatar", authH.AuthRequired(), postsH.UploadAvatar)
	api.GET("/avatar/:filename", postsH.ServeAvatar)
}
