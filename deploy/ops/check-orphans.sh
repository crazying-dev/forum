#!/usr/bin/env bash
# ============================================================
# 媒体孤岛对账（**只出报告，不删除任何对象**）
#
# 检查两个方向：
#   A. S3 有对象、DB 无对应行   → 孤儿对象（白占磁盘）
#   B. DB 有行、S3 无对应对象   → 断链（用户会看到 404/502）
#
# 依赖：aws CLI（S3 列表）+ psql（DB 查询）。任一缺失时打印说明并退出 0。
# 输出：CSV 到 $OUT_DIR（默认 /var/log/yj-ops），并打印统计。
#
# 用法：
#   DATABASE_URL=postgresql://... \
#   S3_ENDPOINT=http://127.0.0.1:8333 S3_BUCKET=yj-forum \
#   AWS_ACCESS_KEY_ID=... AWS_SECRET_ACCESS_KEY=... \
#   bash check-orphans.sh
#
# 说明：本脚本永远不删除对象；确认报告后可人工处理。
# ============================================================
set -euo pipefail

OUT_DIR="${OUT_DIR:-/var/log/yj-ops}"
S3_ENDPOINT="${S3_ENDPOINT:-http://127.0.0.1:8333}"
S3_BUCKET="${S3_BUCKET:-yj-forum}"
DATABASE_URL="${DATABASE_URL:-}"
STAMP="$(date +%Y%m%d-%H%M%S)"

if ! command -v aws >/dev/null 2>&1; then
  echo "[SKIP] 未安装 aws CLI（无法列举 S3 对象），跳过对账"
  exit 0
fi
if ! command -v psql >/dev/null 2>&1; then
  echo "[SKIP] 未安装 psql（无法查询 media_assets），跳过对账"
  exit 0
fi
if [ -z "$DATABASE_URL" ]; then
  echo "[SKIP] 未设置 DATABASE_URL，跳过对账"
  exit 0
fi

mkdir -p "$OUT_DIR"
S3_LIST="$OUT_DIR/s3-objects-$STAMP.txt"
DB_LIST="$OUT_DIR/db-objects-$STAMP.txt"
ORPHANS="$OUT_DIR/orphans-$STAMP.csv"
DANGLING="$OUT_DIR/dangling-$STAMP.csv"

# A) 列出 S3 全部对象 key（只取 Key 列）
aws --endpoint-url "$S3_ENDPOINT" s3api list-objects-v2 \
  --bucket "$S3_BUCKET" --paginate \
  --query 'Contents[].Key' --output text 2>/dev/null \
  | tr '\t' '\n' | sed '/^$/d' | sort -u > "$S3_LIST"

# B) 列出 DB 已知对象 key（原图 + 变体）
psql "$DATABASE_URL" -At -F '' -c "
  SELECT object_key FROM media_assets WHERE COALESCE(object_key,'') <> ''
  UNION
  SELECT object_key FROM media_variants WHERE COALESCE(object_key,'') <> ''
" 2>/dev/null | sed '/^$/d' | sort -u > "$DB_LIST"

# A 方向：S3 有、DB 无
comm -23 "$S3_LIST" "$DB_LIST" | sed '1i object_key,reason' | sed '2,$s/$/,orphan/' > "$ORPHANS"
# B 方向：DB 有、S3 无
comm -13 "$S3_LIST" "$DB_LIST" | sed '1i object_key,reason' | sed '2,$s/$/,missing_object/' > "$DANGLING"

S3_N=$(wc -l < "$S3_LIST" | tr -d ' ')
DB_N=$(wc -l < "$DB_LIST" | tr -d ' ')
ORPHAN_N=$(( $(wc -l < "$ORPHANS") > 0 ? $(wc -l < "$ORPHANS") - 1 : 0 ))
DANGLE_N=$(( $(wc -l < "$DANGLING") > 0 ? $(wc -l < "$DANGLING") - 1 : 0 ))

echo "S3 对象: $S3_N | DB 记录: $DB_N | 孤儿对象: $ORPHAN_N | 断链记录: $DANGLE_N"
echo "报告：$ORPHANS"
echo "报告：$DANGLING"

# 有孤儿/断链时退出 1（便于监控）；但绝不自动删除
if [ "$ORPHAN_N" -gt 0 ] || [ "$DANGLE_N" -gt 0 ]; then
  exit 1
fi
exit 0
