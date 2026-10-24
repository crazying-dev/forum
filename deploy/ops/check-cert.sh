#!/usr/bin/env bash
# ============================================================
# yj-ops：TLS 证书到期巡检
#
# 默认检查公网域名的 443 证书；也可用 CERT_FILES 直接检查本地证书文件。
# 退出码：0 正常/跳过；1 即将到期（WARN）；2 已过期或不可用（CRIT）。
# 可用环境变量：
#   CERT_DOMAINS="yjlt.top www.yjlt.top"   要检查的域名
#   CERT_FILES="/etc/nginx/ssl/yjlt.top.pem"  直接检查的 PEM 文件（优先）
#   CERT_WARN_DAYS=21 / CERT_CRIT_DAYS=7
# ============================================================
set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
CERT_DOMAINS="${CERT_DOMAINS:-yjlt.top www.yjlt.top}"
CERT_FILES="${CERT_FILES:-}"
WARN_DAYS="${CERT_WARN_DAYS:-21}"
CRIT_DAYS="${CERT_CRIT_DAYS:-7}"

exit_code=0
REPORT=''
add() { REPORT+="$1"$'\n'; }

if ! command -v openssl >/dev/null 2>&1; then
    echo '[SKIP] 未安装 openssl，跳过证书检查'
    exit 0
fi

now=$(date +%s)

check_enddate() {
    # check_enddate <label> <notAfter 日期字符串>
    local label="$1" end_raw="$2" end days
    if [[ -z "$end_raw" ]]; then
        echo "[CRIT] ${label}: 无法读取证书到期时间"
        add "[CRIT] ${label}: 无法读取证书到期时间"
        exit_code=2
        return
    fi
    if ! end=$(date -d "$end_raw" +%s 2>/dev/null); then
        echo "[WARN] ${label}: 无法解析到期时间 '${end_raw}'"
        add "[WARN] ${label}: 无法解析到期时间 '${end_raw}'"
        if (( exit_code < 1 )); then exit_code=1; fi
        return
    fi
    days=$(( (end - now) / 86400 ))
    if (( end <= now )); then
        echo "[CRIT] ${label}: 已过期（${end_raw}）"
        add "[CRIT] ${label}: 已过期（${end_raw}）"
        exit_code=2
    elif (( days <= CRIT_DAYS )); then
        echo "[CRIT] ${label}: ${days} 天后到期（${end_raw}）"
        add "[CRIT] ${label}: ${days} 天后到期（${end_raw}）"
        exit_code=2
    elif (( days <= WARN_DAYS )); then
        echo "[WARN] ${label}: ${days} 天后到期（${end_raw}）"
        add "[WARN] ${label}: ${days} 天后到期（${end_raw}）"
        if (( exit_code < 1 )); then exit_code=1; fi
    else
        echo "[OK]   ${label}: ${days} 天后到期（${end_raw}）"
    fi
}

if [[ -n "$CERT_FILES" ]]; then
    for f in $CERT_FILES; do
        if [[ ! -r "$f" ]]; then
            echo "[WARN] 证书文件不可读: ${f}"
            add "[WARN] 证书文件不可读: ${f}"
            if (( exit_code < 1 )); then exit_code=1; fi
            continue
        fi
        end_raw=$(openssl x509 -in "$f" -noout -enddate 2>/dev/null | sed -n 's/^notAfter=//p' || true)
        check_enddate "$f" "$end_raw"
    done
else
    for d in $CERT_DOMAINS; do
        end_raw=$(echo | timeout 10 openssl s_client -servername "$d" -connect "${d}:443" 2>/dev/null \
            | openssl x509 -noout -enddate 2>/dev/null | sed -n 's/^notAfter=//p' || true)
        if [[ -z "$end_raw" ]]; then
            echo "[CRIT] ${d}: 443 握手失败或无法读取证书"
            add "[CRIT] ${d}: 443 握手失败或无法读取证书"
            exit_code=2
            continue
        fi
        check_enddate "$d" "$end_raw"
    done
fi

if (( exit_code > 0 )) && [[ -x "${SCRIPT_DIR}/notify-mail.sh" ]]; then
    severity=$([[ $exit_code -eq 2 ]] && echo CRIT || echo WARN)
    printf '%s\n主机: %s\n时间: %s\n' "$REPORT" "$(hostname)" "$(date '+%F %T')" \
        | "${SCRIPT_DIR}/notify-mail.sh" "[yj-ops][${severity}] 证书告警 $(hostname)" || true
fi

exit "$exit_code"
