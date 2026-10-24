#!/usr/bin/env bash
# ============================================================
# yj-ops：磁盘 / inode 巡检
#
# 检查 / 与 SeaweedFS 数据目录所在文件系统；超过阈值时调用同目录 notify-mail.sh。
# 退出码：0 正常；1 警告；2 严重。
# 可用环境变量：
#   DISK_PATHS="/ /var/lib/seaweedfs"   要检查的路径（空格分隔）
#   DISK_WARN_PCT=80 / DISK_CRIT_PCT=90 使用率阈值
#   INODE_WARN_PCT=90                    inode 使用率阈值
# ============================================================
set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
DISK_PATHS="${DISK_PATHS:-/ /var/lib/seaweedfs}"
WARN_PCT="${DISK_WARN_PCT:-80}"
CRIT_PCT="${DISK_CRIT_PCT:-90}"
INODE_WARN_PCT="${INODE_WARN_PCT:-90}"

exit_code=0
REPORT=''
add() { REPORT+="$1"$'\n'; }

pct_of() {
    # pct_of <path> <df-args...>
    local path="$1"; shift
    df -P "$@" "$path" 2>/dev/null | awk 'NR==2 {gsub("%","",$5); print $5}' || true
}

for p in $DISK_PATHS; do
    if [[ ! -e "$p" ]]; then
        echo "[SKIP] ${p} 不存在"
        continue
    fi
    use=$(pct_of "$p" -B1)
    inode_use=$(pct_of "$p" -Pi)
    avail=$(df -P -B1 "$p" 2>/dev/null | awk 'NR==2 {print $4}' || true)
    if [[ ! "$use" =~ ^[0-9]+$ ]]; then
        echo "[WARN] 无法读取 ${p} 磁盘用量"
        add "[WARN] ${p}: 无法读取磁盘用量"
        if (( exit_code < 1 )); then exit_code=1; fi
        continue
    fi
    avail_gb=$(( ${avail:-0} / 1024 / 1024 / 1024 ))
    level='OK'
    if (( use >= CRIT_PCT )); then
        level='CRIT'; exit_code=2
    elif (( use >= WARN_PCT )); then
        level='WARN'
        if (( exit_code < 1 )); then exit_code=1; fi
    fi
    line="[${level}] ${p} 磁盘使用 ${use}%（可用 ${avail_gb}G）"
    if [[ "$inode_use" =~ ^[0-9]+$ ]] && (( inode_use >= INODE_WARN_PCT )); then
        line+=" inode ${inode_use}%"
        if [[ "$level" == 'OK' ]]; then level='WARN'; fi
        if (( exit_code < 1 )); then exit_code=1; fi
    fi
    echo "$line"
    if [[ "$level" != 'OK' ]]; then add "$line"; fi
done

if (( exit_code > 0 )) && [[ -x "${SCRIPT_DIR}/notify-mail.sh" ]]; then
    severity=$([[ $exit_code -eq 2 ]] && echo CRIT || echo WARN)
    printf '%s\n主机: %s\n时间: %s\n' "$REPORT" "$(hostname)" "$(date '+%F %T')" \
        | "${SCRIPT_DIR}/notify-mail.sh" "[yj-ops][${severity}] 磁盘告警 $(hostname)" || true
fi

exit "$exit_code"
