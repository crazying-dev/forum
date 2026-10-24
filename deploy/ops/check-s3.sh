#!/usr/bin/env bash
# ============================================================
# yj-ops：SeaweedFS S3 / 指标 / bucket / 服务状态巡检
#
# 默认在 Host A 运行（生产 S3 只绑 WireGuard 10.8.0.1）。
# 退出码：0 正常；1 异常（会尝试发邮件）。
# 可用环境变量：
#   S3_ENDPOINT=http://10.8.0.1:8333    S3 根地址
#   METRICS_URL=http://10.8.0.1:9327/metrics
#   S3_BUCKET=yj-forum / MASTER=10.8.0.1:9333
#   CHECK_BUCKET=1（weed 存在时检查 bucket）/ CHECK_TIMEOUT=5
# ============================================================
set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
S3_ENDPOINT="${S3_ENDPOINT:-http://10.8.0.1:8333}"
METRICS_URL="${METRICS_URL:-http://10.8.0.1:9327/metrics}"
S3_BUCKET="${S3_BUCKET:-yj-forum}"
MASTER="${MASTER:-10.8.0.1:9333}"
CHECK_BUCKET="${CHECK_BUCKET:-1}"
TIMEOUT="${CHECK_TIMEOUT:-5}"

fail() { errors+=("$1"); echo "[FAIL] $1"; }
ok()   { echo "[OK]   $1"; }

http_code() {
    curl -s -o /dev/null -w '%{http_code}' --max-time "$TIMEOUT" "$1" 2>/dev/null || true
}

declare -a errors=()

# 1. S3 根（未签名请求 403/200 即存活）
code=$(http_code "${S3_ENDPOINT}/")
if [[ "$code" == '403' || "$code" == '200' ]]; then
    ok "S3 ${S3_ENDPOINT}/ → HTTP ${code}"
else
    fail "S3 ${S3_ENDPOINT}/ 不可用（HTTP ${code:-无响应}）"
fi

# 2. 指标端点
code=$(http_code "$METRICS_URL")
if [[ "$code" == '200' ]]; then
    body=$(curl -s --max-time "$TIMEOUT" "$METRICS_URL" 2>/dev/null | head -c 200 || true)
    if [[ -n "$body" ]]; then
        ok "指标 ${METRICS_URL} → HTTP 200"
    else
        fail "指标 ${METRICS_URL} 返回空内容"
    fi
else
    fail "指标 ${METRICS_URL} 不可用（HTTP ${code:-无响应}）"
fi

# 3. systemd 服务（存在该 unit 时才检查）
if command -v systemctl >/dev/null 2>&1 \
    && systemctl list-unit-files seaweedfs.service 2>/dev/null | grep -q '^seaweedfs\.service'; then
    state=$(systemctl is-active seaweedfs 2>/dev/null || true)
    if [[ "$state" == 'active' ]]; then
        ok 'seaweedfs.service active'
    else
        fail "seaweedfs.service 状态 ${state:-unknown}"
    fi
fi

# 4. bucket（需要本机有 weed）
if [[ "$CHECK_BUCKET" == '1' ]] && command -v weed >/dev/null 2>&1; then
    buckets=$(printf 's3.bucket.list\n' | timeout 20 weed shell -master="$MASTER" 2>/dev/null || true)
    if printf '%s\n' "$buckets" | awk -v b="$S3_BUCKET" '$1 == b { found = 1 } END { exit(found ? 0 : 1) }'; then
        ok "bucket ${S3_BUCKET} 存在"
    else
        fail "bucket ${S3_BUCKET} 未在 s3.bucket.list 中找到"
    fi
fi

if (( ${#errors[@]} > 0 )); then
    if [[ -x "${SCRIPT_DIR}/notify-mail.sh" ]]; then
        printf '%s\n主机: %s\n时间: %s\n' "$(printf '%s\n' "${errors[@]}")" "$(hostname)" "$(date '+%F %T')" \
            | "${SCRIPT_DIR}/notify-mail.sh" "[yj-ops][CRIT] S3 异常 $(hostname)" || true
    fi
    exit 1
fi

exit 0
