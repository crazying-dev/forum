package handler

import (
	"context"
	"html"
	"log"
	"net/http"
	"strings"
	"time"

	"github.com/gin-gonic/gin"
	"github.com/jackc/pgx/v5"

	"yj-forum/server/internal/database"
	"yj-forum/server/internal/email"
	"yj-forum/server/internal/models"
	"yj-forum/server/internal/sanitize"
)

// maxCommentContentBytes 评论原始正文长度上限（64KB，与发帖富文本一致）。
const maxCommentContentBytes = 64 * 1024

// ---- GET /api/v1/posts/:id/comments ----

// Comments 评论列表（匿名缓存 comments:post:ID；登录用户实时返回含 liked_by_me）。
func (h *PostsHandler) Comments(c *gin.Context) {
	id := c.Param("id")
	page, _ := parsePage(c)
	pageSize := 50
	me := currentUserFromCookie(c, h.Sessions)
	// 定时未发布帖（非作者视角）与不存在的帖子：评论列表同样 404
	if !h.postVisible(c, id, me) {
		return
	}
	key := "comments:post:" + id + ":" + itoa(page)
	if me == "" {
		if v, ok := h.Cache.Comments.Get(key); ok {
			c.Header("X-Cache", "HIT")
			c.JSON(http.StatusOK, v)
			return
		}
	}
	comments, err := h.DB.GetPostComments(c.Request.Context(), id, page, pageSize)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"success": false, "message": "查询失败"})
		return
	}
	resp := gin.H{"success": true, "comments": comments, "page": page, "page_size": pageSize}
	if me != "" {
		// 含个人点赞状态，不走共享缓存
		markCommentLikedByMe(h.DB, c.Request.Context(), me, comments)
		c.Header("X-Cache", "BYPASS")
	} else {
		h.Cache.Comments.Set(key, resp, 60*time.Second)
		c.Header("X-Cache", "MISS")
	}
	c.JSON(http.StatusOK, resp)
}

// ---- POST /api/v1/posts/:id/comments ----

type createCommentReq struct {
	Content  string  `json:"content" binding:"required"`
	ParentID *string `json:"parent_id"`
	Altcha   string  `json:"altcha"`
	Grant    string  `json:"grant"`
}

// CreateComment 评论/回复（富文本，与发帖共用净化白名单）。
func (h *PostsHandler) CreateComment(c *gin.Context) {
	uid := CurrentUser(c)
	if uid == "" {
		c.JSON(http.StatusUnauthorized, gin.H{"success": false, "message": "请先登录"})
		return
	}
	postID := c.Param("id")
	// 定时未发布帖（非作者视角）与不存在的帖子不可评论
	if !h.postVisible(c, postID, uid) {
		return
	}
	var req createCommentReq
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"success": false, "message": "参数错误"})
		return
	}
	// ALTCHA 人机验证（启用时 fail-closed；未启用保持原行为）
	if !VerifyRequest(c, h.Altcha, req.Altcha, req.Grant) {
		c.JSON(http.StatusBadRequest, gin.H{"success": false, "message": "请先完成人机验证"})
		return
	}
	// 原始 HTML 长度上限
	if len(req.Content) > maxCommentContentBytes {
		c.JSON(http.StatusBadRequest, gin.H{"success": false, "message": "内容过长"})
		return
	}
	// 富文本净化（与发帖一致）；纯文本需 1-500 字，纯图片/纯引用卡视为有效
	content := sanitize.SanitizeRichContent(strings.TrimSpace(req.Content))
	// 内容节点上限（净化后计数）：防超大 DOM 结构拖垮渲染与存储
	if strings.Count(content, "<img") > 20 || strings.Count(content, "data-embed=") > 10 {
		c.JSON(http.StatusBadRequest, gin.H{"success": false, "message": "图片/引用数量过多"})
		return
	}
	plain := sanitize.StripTagsAndTrim(content)
	plainLen := len([]rune(plain))
	hasRichMedia := strings.Contains(content, "<img") || strings.Contains(content, "data-embed")
	if plainLen > 500 || (plainLen == 0 && !hasRichMedia) {
		c.JSON(http.StatusBadRequest, gin.H{"success": false, "message": "内容需1-500字符"})
		return
	}
	// 回复校验：父评论必须存在、与本帖同帖且未删除
	parentID := req.ParentID
	if parentID != nil && strings.TrimSpace(*parentID) == "" {
		parentID = nil
	}
	if parentID != nil {
		parentPostID, parentStatus, err := h.DB.GetCommentPostAndStatus(c.Request.Context(), *parentID)
		if err != nil || parentPostID != postID || parentStatus != 1 {
			c.JSON(http.StatusBadRequest, gin.H{"success": false, "message": "回复的评论不存在或已删除"})
			return
		}
	}
	comment, err := h.DB.AddComment(c.Request.Context(), postID, uid, content, "html", parentID)
	if err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"success": false, "message": "评论失败"})
		return
	}
	// 评论/回复灵力 +3（source=commentID 幂等）
	h.awardCommentSpirit(c.Request.Context(), uid, comment.ID)
	// 异步通知（站内通知 + 邮件 outbox）
	go h.notifyComment(comment)
	h.Cache.Comments.DeletePrefix("comments:post:" + postID)
	h.Cache.PostDetail.Delete("post:detail:" + postID)
	c.JSON(http.StatusCreated, gin.H{"success": true, "comment": comment})
}

// awardCommentSpirit 评论/回复灵力奖励（comment +3，按 source=commentID 幂等）。
func (h *PostsHandler) awardCommentSpirit(ctx context.Context, userID, commentID string) {
	awarded, amount, err := h.DB.AwardSpirit(ctx, userID, "comment", commentID)
	if err != nil {
		log.Printf("[SPIRIT] 评论奖励失败 comment=%s: %v", commentID, err)
		return
	}
	if awarded {
		log.Printf("[SPIRIT] 评论奖励 +%d (user=%s comment=%s)", amount, userID, commentID)
	}
}

// notifyComment 评论通知：给帖子作者/父评论作者写站内通知，并在同一事务内入队邮件 outbox。
// 邮件 outbox 入队失败时回退到旧的直发逻辑（保证通知不丢）。
func (h *PostsHandler) notifyComment(comment *models.Comment) {
	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()
	// 回复则通知父评论作者，否则通知帖子作者；跳过自己给自己评论/回复自己的情况
	var targetUserID, targetEmail string
	notifType := database.NotificationPostComment
	if comment.ParentID != nil && *comment.ParentID != "" {
		notifType = database.NotificationCommentReply
		pc, err := h.DB.GetComment(ctx, *comment.ParentID)
		if err == nil && pc != nil {
			u, err2 := h.DB.GetUserByID(ctx, pc.UserID)
			if err2 == nil {
				targetUserID = u.ID
				targetEmail = u.Email
			}
		}
	} else {
		post, err := h.DB.GetPost(ctx, comment.PostID)
		if err == nil && post != nil {
			u, err2 := h.DB.GetUserByID(ctx, post.UserID)
			if err2 == nil {
				targetUserID = u.ID
				targetEmail = u.Email
			}
		}
	}
	if targetUserID == "" || targetUserID == comment.UserID {
		return
	}

	postTitle := ""
	if post, err := h.DB.GetPost(ctx, comment.PostID); err == nil && post != nil {
		postTitle = post.Title
	}
	excerpt := truncateRunes(sanitize.StripTagsAndTrim(comment.Content), 200)
	authorName := comment.UserName
	if authorName == "" {
		if u, err := h.DB.GetUserByID(ctx, comment.UserID); err == nil && u != nil {
			authorName = u.Name
		}
	}
	link := "https://" + h.Cfg.PublicBaseURL + "/post/" + comment.PostID
	verb := "评论了你的帖子"
	subject := "【妖精论坛】你的帖子收到新评论"
	if notifType == database.NotificationCommentReply {
		verb = "回复了你的评论"
		subject = "【妖精论坛】收到新回复"
	}
	plain := authorName + " " + verb + "：\n" + excerpt + "\n" + link
	htmlBody := email.BuildHTML("评论通知", authorName+" "+verb,
		[]string{"<strong>" + html.EscapeString(authorName) + "</strong> " + verb + "：", html.EscapeString(excerpt), "点击查看详情"},
		"查看帖子", link, "")

	var notifID int64
	created := false
	err := h.DB.Tx(ctx, func(tx pgx.Tx) error {
		id, ok, e := h.DB.CreateNotificationTx(ctx, tx, database.NotificationInput{
			UserID: targetUserID, Type: notifType, ActorID: comment.UserID,
			TargetType: "comment", TargetID: comment.ID,
			ContextPostID: comment.PostID, ContextCommentID: comment.ID,
			Payload: map[string]any{
				"post_title": postTitle, "excerpt": excerpt, "actor_name": authorName,
				"parent_id": parentIDString(comment.ParentID),
			},
			DedupeKey: "comment_notify:" + comment.ID,
		})
		if e != nil {
			return e
		}
		notifID, created = id, ok
		if !ok || targetEmail == "" {
			return nil
		}
		if _, e = h.DB.EnqueueEmailTx(ctx, tx, database.EmailOutboxInput{
			To:        []string{targetEmail},
			Subject:   subject,
			PlainBody: plain,
			HTMLBody:  htmlBody,
			DedupeKey: "comment_notify_mail:" + comment.ID,
		}); e != nil {
			return e
		}
		return nil
	})
	if err != nil {
		log.Printf("[COMMENT] 通知/outbox 写入失败 comment=%s: %v", comment.ID, err)
		// 回退：直接发信（旧逻辑），避免邮件通知完全丢失
		if targetEmail != "" {
			_, _ = h.Mailer.Send(subject, plain, []string{targetEmail}, htmlBody)
		}
		return
	}
	if created {
		PushNotificationEvent(targetUserID, notifID, gin.H{
			"id": notifID, "type": notifType, "actor_id": comment.UserID, "actor_name": authorName,
			"target_type": "comment", "target_id": comment.ID, "comment_id": comment.ID,
			"post_id": comment.PostID, "post_title": postTitle, "excerpt": excerpt,
			"parent_id": parentIDString(comment.ParentID),
		})
		PushUnreadEvent(ctx, h.DB, targetUserID)
	}
}

func parentIDString(parent *string) string {
	if parent == nil {
		return ""
	}
	return *parent
}

// ---- DELETE /api/v1/comments/:id ----

// DeleteComment 删除评论（仅作者）。
func (h *PostsHandler) DeleteComment(c *gin.Context) {
	uid := CurrentUser(c)
	if uid == "" {
		c.JSON(http.StatusUnauthorized, gin.H{"success": false, "message": "请先登录"})
		return
	}
	id := c.Param("id")
	comment, _ := h.DB.GetComment(c.Request.Context(), id)
	ok, err := h.DB.DeleteComment(c.Request.Context(), id, uid)
	if err != nil || !ok {
		c.JSON(http.StatusForbidden, gin.H{"success": false, "message": "无权限删除该评论"})
		return
	}
	// 使评论列表与帖子详情缓存失效
	if comment != nil {
		h.Cache.Comments.DeletePrefix("comments:post:" + comment.PostID)
		h.Cache.PostDetail.Delete("post:detail:" + comment.PostID)
	}
	c.JSON(http.StatusOK, gin.H{"success": true})
}

// ---- POST /api/v1/comments/:id/like ----

// LikeComment 评论点赞切换。
func (h *PostsHandler) LikeComment(c *gin.Context) {
	uid := CurrentUser(c)
	if uid == "" {
		c.JSON(http.StatusUnauthorized, gin.H{"success": false, "message": "请先登录"})
		return
	}
	id := c.Param("id")
	comment, err := h.DB.GetComment(c.Request.Context(), id)
	if err != nil || comment == nil || comment.Status != 1 {
		c.JSON(http.StatusNotFound, gin.H{"success": false, "message": "评论不存在"})
		return
	}
	liked, likes, err := h.DB.LikeComment(c.Request.Context(), id, uid)
	if err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"success": false, "message": "操作失败"})
		return
	}
	if liked {
		h.notifyCommentLike(c.Request.Context(), comment, uid)
	}
	// 使评论列表与帖子详情缓存失效
	h.Cache.Comments.DeletePrefix("comments:post:" + comment.PostID)
	h.Cache.PostDetail.Delete("post:detail:" + comment.PostID)
	c.JSON(http.StatusOK, gin.H{"success": true, "liked": liked, "likes": likes})
}

// notifyCommentLike 评论点赞后给评论作者写站内通知（跳过自赞；dedupe 防重复）。
func (h *PostsHandler) notifyCommentLike(ctx context.Context, comment *models.Comment, actorID string) {
	if comment == nil || comment.UserID == "" || comment.UserID == actorID {
		return
	}
	title := ""
	if post, err := h.DB.GetPost(ctx, comment.PostID); err == nil && post != nil {
		title = post.Title
	}
	excerpt := truncateRunes(sanitize.StripTagsAndTrim(comment.Content), 120)
	actorName, actorAvatar := actorID, ""
	if u, err := h.DB.GetUserByID(ctx, actorID); err == nil && u != nil {
		actorName, actorAvatar = u.Name, u.Avatar
	}
	in := database.NotificationInput{
		UserID: comment.UserID, Type: database.NotificationCommentLike, ActorID: actorID,
		TargetType: "comment", TargetID: comment.ID,
		ContextPostID: comment.PostID, ContextCommentID: comment.ID,
		Payload:   map[string]any{"post_title": title, "excerpt": excerpt, "actor_name": actorName},
		DedupeKey: "comment_like:" + comment.ID + ":" + actorID,
	}
	notifID, created, err := h.DB.CreateNotification(ctx, in)
	if err != nil || !created {
		return
	}
	PushNotificationEvent(comment.UserID, notifID, gin.H{
		"id": notifID, "type": in.Type, "actor_id": actorID, "actor_name": actorName, "actor_avatar": actorAvatar,
		"target_type": "comment", "target_id": comment.ID, "comment_id": comment.ID,
		"post_id": comment.PostID, "post_title": title, "comment_excerpt": excerpt,
	})
	PushUnreadEvent(ctx, h.DB, comment.UserID)
}

// markCommentLikedByMe 批量填充评论的 liked_by_me。
func markCommentLikedByMe(db *database.DB, ctx context.Context, me string, comments []models.Comment) {
	if len(comments) == 0 {
		return
	}
	ids := make([]string, 0, len(comments))
	for i := range comments {
		ids = append(ids, comments[i].ID)
	}
	liked, err := db.GetLikedCommentIDs(ctx, me, ids)
	if err != nil {
		return
	}
	for i := range comments {
		comments[i].LikedByMe = liked[comments[i].ID]
	}
}
