package handler

import (
	"context"
	"log"

	"yj-forum/server/internal/database"
)

// verifyCodeMaxAttempts 单个验证码允许的最大失败次数；达到后作废该验证码，需重新获取。
const verifyCodeMaxAttempts = 5

// verifyCodeWithLimit 校验验证码并限制失败次数（注册/邮箱验证/邮箱换绑共用）：
// - 失败次数达上限：直接拒绝（有效验证码已在最后一次失败时作废）；
// - 校验失败：累计失败次数，达到上限即作废当前验证码；
// - 校验成功：核销验证码。
// 返回 ok=false 表示验证码错误/已过期/尝试过多（调用方统一返回“验证码错误或已过期”）；err 为基础设施错误。
func verifyCodeWithLimit(ctx context.Context, db *database.DB, email, code, purpose string) (bool, error) {
	attempts, err := db.GetActiveVerifyCodeAttempts(ctx, email, purpose)
	if err != nil {
		return false, err
	}
	if attempts >= verifyCodeMaxAttempts {
		return false, nil
	}
	// 原子核销：并发重复提交时只有一个请求能成功。
	ok, err := db.ConsumeVerifyCode(ctx, email, code, purpose)
	if err != nil {
		return false, err
	}
	if !ok {
		if err := db.BumpActiveVerifyCodeAttempts(ctx, email, purpose); err != nil {
			log.Printf("[CODE] 验证码尝试次数累计失败 (%s/%s): %v", email, purpose, err)
		}
		if attempts+1 >= verifyCodeMaxAttempts {
			if err := db.InvalidateActiveVerifyCodes(ctx, email, purpose); err != nil {
				log.Printf("[CODE] 验证码作废失败 (%s/%s): %v", email, purpose, err)
			}
		}
		return false, nil
	}
	return true, nil
}
