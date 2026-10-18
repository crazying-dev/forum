// Package queue 实现基于 PostgreSQL 的后台消费者：
// email_outbox（5s/20 条，失败指数退避）、email_fanout_jobs（展开 follower_post）、cache_invalidations（1s/50 条）。
package queue

import (
	"context"
	"fmt"
	"log"
	"os"
	"strings"
	"time"

	"github.com/jackc/pgx/v5"

	"yj-forum/server/internal/database"
	"yj-forum/server/internal/email"
)

const (
	emailBatchSize  = 20
	fanoutBatchSize = 10
	cacheBatchSize  = 50

	emailInterval  = 5 * time.Second
	fanoutInterval = 5 * time.Second
	cacheInterval  = 1 * time.Second

	maxEmailAttempts = 8
	// fanout 的最大尝试次数在 database.MarkFanoutDone 中固定为 5
)

// CacheInvalidator 缓存失效执行器（生产实现为 *handler.CacheSet，测试可注入 mock）。
type CacheInvalidator interface {
	Invalidate(scope, key string) bool
}

// Start 启动 outbox / fanout / cache invalidation 三个消费者，直到 ctx 取消。
// cacheSet 为 nil 时 cache 消费者仍会运行（记录失败并在 5 次后标记死信）。
func Start(ctx context.Context, db *database.DB, mailer *email.Sender, cacheSet CacheInvalidator) {
	if db == nil {
		log.Println("[QUEUE] db 未注入，后台消费者未启动")
		return
	}
	go loop(ctx, emailInterval, func(ctx context.Context) {
		if n, err := ProcessEmailBatch(ctx, db, mailer, emailBatchSize); err != nil {
			log.Printf("[QUEUE] outbox 处理失败: %v", err)
		} else if n > 0 {
			log.Printf("[QUEUE] outbox 已处理 %d 封", n)
		}
	})
	go loop(ctx, fanoutInterval, func(ctx context.Context) {
		if n, err := ProcessFanoutBatch(ctx, db, fanoutBatchSize); err != nil {
			log.Printf("[QUEUE] fanout 处理失败: %v", err)
		} else if n > 0 {
			log.Printf("[QUEUE] fanout 已处理 %d 个任务", n)
		}
	})
	go loop(ctx, cacheInterval, func(ctx context.Context) {
		if n, err := ProcessCacheInvalidations(ctx, db, cacheSet, cacheBatchSize); err != nil {
			log.Printf("[QUEUE] cache 失效处理失败: %v", err)
		} else if n > 0 {
			log.Printf("[QUEUE] cache 失效已处理 %d 条", n)
		}
	})
}

func loop(ctx context.Context, interval time.Duration, fn func(context.Context)) {
	ticker := time.NewTicker(interval)
	defer ticker.Stop()
	fn(ctx)
	for {
		select {
		case <-ctx.Done():
			return
		case <-ticker.C:
			fn(ctx)
		}
	}
}

// ProcessEmailBatch 认领并发送一批 outbox 邮件；失败按指数退避回队，超过上限进死信。
func ProcessEmailBatch(ctx context.Context, db *database.DB, mailer *email.Sender, limit int) (int, error) {
	if db == nil {
		return 0, fmt.Errorf("queue: db 为 nil")
	}
	items, err := db.ClaimEmailBatch(ctx, limit)
	if err != nil {
		return 0, err
	}
	sent := 0
	for _, item := range items {
		if mailer == nil {
			_ = db.MarkEmailFailed(ctx, item.ID, "mailer 未注入", retryAt(time.Now(), item.Attempts))
			continue
		}
		ok, sendErr := mailer.Send(item.Subject, item.PlainBody, []string{item.ToEmail}, item.HTMLBody)
		if sendErr != nil {
			if item.Attempts >= maxEmailAttempts {
				_ = db.MarkEmailFailed(ctx, item.ID, sendErr.Error(), time.Time{})
			} else {
				_ = db.MarkEmailFailed(ctx, item.ID, sendErr.Error(), retryAt(time.Now(), item.Attempts))
			}
			continue
		}
		if !ok {
			// SMTP 未启用时 Sender 返回 (false, nil)：标记失败但保留内容，启用后可人工重放
			if item.Attempts >= maxEmailAttempts {
				_ = db.MarkEmailFailed(ctx, item.ID, "SMTP 未启用", time.Time{})
			} else {
				_ = db.MarkEmailFailed(ctx, item.ID, "SMTP 未启用", retryAt(time.Now(), item.Attempts))
			}
			continue
		}
		if err := db.MarkEmailSent(ctx, item.ID); err != nil {
			log.Printf("[QUEUE] 标记邮件已发送失败 id=%d: %v", item.ID, err)
			continue
		}
		sent++
	}
	return sent, nil
}

// retryAt 指数退避：30s * 2^(attempts-1)，上限 1h。
func retryAt(now time.Time, attempts int) time.Time {
	if attempts < 1 {
		attempts = 1
	}
	d := 30 * time.Second << uint(attempts-1)
	if d <= 0 || d > time.Hour {
		d = time.Hour
	}
	return now.Add(d)
}

// ProcessFanoutBatch 认领并展开 fanout job（当前仅 follower_post）。
func ProcessFanoutBatch(ctx context.Context, db *database.DB, limit int) (int, error) {
	if db == nil {
		return 0, fmt.Errorf("queue: db 为 nil")
	}
	jobs, err := db.ClaimFanoutJobs(ctx, limit)
	if err != nil {
		return 0, err
	}
	done := 0
	for _, job := range jobs {
		err := processFanoutJob(ctx, db, job)
		if err != nil {
			// MarkFanoutDone 依据 attempts 自动决定回队/死信（>=maxFanoutAttempts 进死信）
			_ = db.MarkFanoutDone(ctx, job.ID, err.Error())
			log.Printf("[QUEUE] fanout job=%d 失败: %v", job.ID, err)
			continue
		}
		if err := db.MarkFanoutDone(ctx, job.ID, ""); err != nil {
			log.Printf("[QUEUE] 标记 fanout 完成失败 id=%d: %v", job.ID, err)
			continue
		}
		done++
	}
	return done, nil
}

func processFanoutJob(ctx context.Context, db *database.DB, job database.FanoutJob) error {
	switch job.Kind {
	case "follower_post":
		return expandFollowerPost(ctx, db, job.RefID, job.ActorID)
	default:
		return fmt.Errorf("未知 fanout kind: %s", job.Kind)
	}
}

func expandFollowerPost(ctx context.Context, db *database.DB, postID, actorID string) error {
	post, err := db.GetFanoutPost(ctx, postID)
	if err != nil {
		return err
	}
	if post == nil {
		// 帖子已删除：任务直接完成
		return nil
	}
	if actorID == "" {
		actorID = post.AuthorID
	}
	emails, err := db.ListFollowerEmails(ctx, actorID, 5000)
	if err != nil {
		return err
	}
	if len(emails) == 0 {
		return nil
	}
	author := post.AuthorName
	if author == "" {
		author = "你关注的用户"
	}
	link := publicURL("/post/" + post.ID)
	subject := "【妖精论坛】你关注的 " + author + " 发布了新帖"
	plain := author + " 发布了新帖《" + post.Title + "》\n" + link
	htmlBody := email.BuildHTML("新帖通知", author+" 发布了新帖",
		[]string{"你关注的 <strong>" + htmlEscape(author) + "</strong> 发布了新帖：", "《" + htmlEscape(post.Title) + "》"},
		"查看帖子", link, "你收到这封邮件是因为关注了 TA")

	return db.Tx(ctx, func(tx pgx.Tx) error {
		for _, to := range emails {
			if _, err := db.EnqueueEmailTx(ctx, tx, database.EmailOutboxInput{
				To:        []string{to},
				Subject:   subject,
				PlainBody: plain,
				HTMLBody:  htmlBody,
				DedupeKey: "follower_post:" + post.ID + ":" + to,
			}); err != nil {
				return err
			}
		}
		return nil
	})
}

func publicURL(path string) string {
	base := strings.TrimRight(os.Getenv("PUBLIC_BASE_URL"), "/")
	if base == "" {
		return path
	}
	if !strings.HasPrefix(path, "/") {
		path = "/" + path
	}
	return base + path
}

func htmlEscape(s string) string {
	r := strings.NewReplacer("&", "&amp;", "<", "&lt;", ">", "&gt;", `"`, "&quot;", "'", "&#39;")
	return r.Replace(s)
}

// ProcessCacheInvalidations 认领并执行 cache_invalidations 指令。
func ProcessCacheInvalidations(ctx context.Context, db *database.DB, cacheSet CacheInvalidator, limit int) (int, error) {
	if db == nil {
		return 0, fmt.Errorf("queue: db 为 nil")
	}
	items, err := db.ClaimCacheInvalidations(ctx, limit)
	if err != nil {
		return 0, err
	}
	done := 0
	for _, item := range items {
		if cacheSet == nil {
			_ = db.MarkCacheInvalidation(ctx, item.ID, "cacheSet 未注入")
			continue
		}
		if !cacheSet.Invalidate(item.Scope, item.Key) {
			_ = db.MarkCacheInvalidation(ctx, item.ID, fmt.Sprintf("未知缓存域 %q", item.Scope))
			continue
		}
		if err := db.MarkCacheInvalidation(ctx, item.ID, ""); err != nil {
			log.Printf("[QUEUE] 标记 cache 失效完成失败 id=%d: %v", item.ID, err)
			continue
		}
		done++
	}
	return done, nil
}
