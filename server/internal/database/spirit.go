package database

import (
	"context"
	"errors"
	"fmt"
	"time"

	"github.com/jackc/pgx/v5"
)

// AwardSpiritTx 在事务内发放灵力奖励。
//
// 并发安全：先对 user_id 取事务级 advisory lock（hashtext），串行化同一用户的奖励；
// 幂等：spirit_awards 的 (action, source_id) 唯一约束保证同一来源只奖励一次；
// 日上限：spirit_daily_usage 累计当日已发放量，最多补足到 spirit_rules.daily_cap。
//
// 返回 awarded=false 表示重复来源、达到日上限或规则不存在；amount 为本次实际发放值。
func (d *DB) AwardSpiritTx(ctx context.Context, tx pgx.Tx, userID, action, sourceID string) (awarded bool, amount int, err error) {
	if userID == "" || action == "" || sourceID == "" {
		return false, 0, fmt.Errorf("spirit: user/action/source 不能为空")
	}

	// hashtext 返回 int4，显式转 int8 以匹配 pg_advisory_xact_lock(bigint)。
	if _, err := tx.Exec(ctx, `SELECT pg_advisory_xact_lock(hashtext($1)::bigint)`, userID); err != nil {
		return false, 0, fmt.Errorf("spirit: advisory lock: %w", err)
	}

	var ruleAmount, dailyCap int
	err = tx.QueryRow(ctx, `SELECT amount, daily_cap FROM spirit_rules WHERE action = $1`, action).Scan(&ruleAmount, &dailyCap)
	if errors.Is(err, pgx.ErrNoRows) {
		// 未配置规则：不奖励，也不视为调用失败（例如新动作尚未上线）。
		return false, 0, nil
	}
	if err != nil {
		return false, 0, fmt.Errorf("spirit: 读取规则: %w", err)
	}

	// 来源去重：已存在则直接返回。
	var existing int
	err = tx.QueryRow(ctx, `SELECT amount FROM spirit_awards WHERE action = $1 AND source_id = $2`, action, sourceID).Scan(&existing)
	if err == nil {
		return false, 0, nil
	}
	if !errors.Is(err, pgx.ErrNoRows) {
		return false, 0, fmt.Errorf("spirit: 查询来源: %w", err)
	}

	var dayKey time.Time
	if err := tx.QueryRow(ctx, `SELECT (CURRENT_TIMESTAMP AT TIME ZONE 'Asia/Shanghai')::date`).Scan(&dayKey); err != nil {
		return false, 0, fmt.Errorf("spirit: 计算日界: %w", err)
	}

	var used int
	err = tx.QueryRow(ctx, `SELECT COALESCE(SUM(awarded), 0) FROM spirit_daily_usage
		WHERE user_id = $1 AND action = $2 AND day_key = $3`, userID, action, dayKey).Scan(&used)
	if err != nil {
		return false, 0, fmt.Errorf("spirit: 查询日用量: %w", err)
	}
	remaining := dailyCap - used
	if remaining <= 0 {
		return false, 0, nil
	}
	amount = ruleAmount
	if amount > remaining {
		amount = remaining
	}

	tag, err := tx.Exec(ctx, `INSERT INTO spirit_awards (user_id, action, amount, day_key, source_id)
		VALUES ($1, $2, $3, $4, $5)
		ON CONFLICT (action, source_id) DO NOTHING`, userID, action, amount, dayKey, sourceID)
	if err != nil {
		return false, 0, fmt.Errorf("spirit: 写流水: %w", err)
	}
	if tag.RowsAffected() == 0 {
		// 其他用户并发占用了同一 source（理论上 action+source 唯一）
		return false, 0, nil
	}

	if _, err := tx.Exec(ctx, `INSERT INTO spirit_daily_usage (user_id, action, day_key, awarded)
		VALUES ($1, $2, $3, $4)
		ON CONFLICT (user_id, action, day_key) DO UPDATE
		SET awarded = spirit_daily_usage.awarded + EXCLUDED.awarded`, userID, action, dayKey, amount); err != nil {
		return false, 0, fmt.Errorf("spirit: 累计日用量: %w", err)
	}

	tag, err = tx.Exec(ctx, `UPDATE users SET spirit = spirit + $2 WHERE id = $1`, userID, amount)
	if err != nil {
		return false, 0, fmt.Errorf("spirit: 更新用户灵力: %w", err)
	}
	if tag.RowsAffected() == 0 {
		return false, 0, fmt.Errorf("spirit: 用户不存在 %s", userID)
	}
	return true, amount, nil
}

// AwardSpirit 非事务便捷入口（内部开启事务）。
func (d *DB) AwardSpirit(ctx context.Context, userID, action, sourceID string) (awarded bool, amount int, err error) {
	err = d.Tx(ctx, func(tx pgx.Tx) error {
		var e error
		awarded, amount, e = d.AwardSpiritTx(ctx, tx, userID, action, sourceID)
		return e
	})
	return awarded, amount, err
}
