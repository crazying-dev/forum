#!/usr/bin/env bash
# ============================================================
# yj-forum-ouo 生产原生部署 —— 卸载 SeaweedFS
#
# 默认 dry-run（只打印计划）。必须 --apply 才执行。
# 默认保留数据与配置：/var/lib/seaweedfs、/etc/seaweedfs
# 只有 --purge 才删除上述目录并移除系统用户 seaweedfs。
#
# 用法：
#   bash deploy/native/uninstall-weed.sh                 # 看计划
#   sudo bash deploy/native/uninstall-weed.sh --apply   # 卸服务/二进制，保留数据
#   sudo bash deploy/native/uninstall-weed.sh --apply --purge   # 连数据一起删
# ============================================================
set -euo pipefail

SVC_NAME='seaweedfs'
SVC_USER='seaweedfs'
PREFIX='/opt/seaweedfs'
UNIT_PATH="/etc/systemd/system/${SVC_NAME}.service"
CONF_DIR='/etc/seaweedfs'
STATE_DIR='/var/lib/seaweedfs'
DATA_DIR='/var/lib/seaweedfs/data'
BIN_LINK='/usr/local/bin/weed'

DRY_RUN=1
PURGE=0

die()  { printf '[ERROR] %s\n' "$*" >&2; exit 1; }
info() { printf '[INFO] %s\n' "$*"; }
warn() { printf '[WARN] %s\n' "$*"; }
plan() { printf '[plan] %s\n' "$*"; }
run()  { if (( DRY_RUN )); then plan "$*"; else "$@"; fi; }

usage() {
    cat <<'EOF'
用法: bash deploy/native/uninstall-weed.sh [--apply] [--purge]

  --apply   真正执行（默认 dry-run，只打印计划；需要 root）
  --purge   额外删除 /var/lib/seaweedfs（数据）与 /etc/seaweedfs（配置），
            并移除系统用户 seaweedfs。默认保留。
  -h|--help 显示帮助
EOF
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --dry-run) DRY_RUN=1; shift ;;
        --apply)   DRY_RUN=0; shift ;;
        --purge)   PURGE=1; shift ;;
        -h|--help) usage; exit 0 ;;
        *) die "未知参数: $1（--help 查看用法）" ;;
    esac
done

if (( ! DRY_RUN )); then
    (( EUID == 0 )) || die '--apply 需要 root 权限，请使用 sudo 执行'
fi

printf '=== SeaweedFS 卸载（%s%s）===\n' \
    "$([[ $DRY_RUN -eq 1 ]] && echo 'dry-run，不修改系统' || echo 'APPLY')" \
    "$([[ $PURGE -eq 1 ]] && echo '，--purge 删数据' || echo '，保留数据')"

# 1. 停止并禁用服务
if systemctl list-unit-files "${SVC_NAME}.service" >/dev/null 2>&1 \
    && systemctl list-unit-files "${SVC_NAME}.service" | grep -q "^${SVC_NAME}\.service"; then
    if (( DRY_RUN )); then
        plan "systemctl disable --now ${SVC_NAME}"
    else
        systemctl disable --now "$SVC_NAME" 2>/dev/null || systemctl stop "$SVC_NAME" 2>/dev/null || true
        info "已停止并禁用 ${SVC_NAME}"
    fi
else
    info "未发现 ${SVC_NAME}.service，跳过停止"
fi

# 2. 移除 unit
if [[ -f "$UNIT_PATH" ]]; then
    run rm -f "$UNIT_PATH"
    if (( ! DRY_RUN )); then
        systemctl daemon-reload
        info "已移除 ${UNIT_PATH}"
    fi
else
    info "未发现 ${UNIT_PATH}"
fi

# 3. 移除软链与二进制
if [[ -L "$BIN_LINK" || -f "$BIN_LINK" ]]; then
    run rm -f "$BIN_LINK"
else
    info "未发现 ${BIN_LINK}"
fi
if [[ -d "$PREFIX" ]]; then
    run rm -rf "$PREFIX"
else
    info "未发现 ${PREFIX}"
fi

# 4. 数据/配置
if (( PURGE )); then
    warn '--purge：即将删除数据目录与配置目录（不可恢复）'
    [[ -d "$STATE_DIR" ]] && run rm -rf "$STATE_DIR" || info "未发现 ${STATE_DIR}"
    [[ -d "$CONF_DIR" ]] && run rm -rf "$CONF_DIR" || info "未发现 ${CONF_DIR}"
    if id -u "$SVC_USER" >/dev/null 2>&1; then
        run userdel "$SVC_USER"
    else
        info "用户 ${SVC_USER} 不存在"
    fi
else
    info "保留数据: ${DATA_DIR}"
    info "保留配置: ${CONF_DIR}/s3.json"
    info "如需一并删除：重新执行并加 --purge --apply"
fi

printf '\n=== %s ===\n' "$([[ $DRY_RUN -eq 1 ]] && echo 'dry-run 完成（未修改系统）' || echo '卸载完成')"
