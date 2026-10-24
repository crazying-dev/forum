#!/usr/bin/env bash
# ============================================================
# yj-forum-ouo 生产原生部署 —— 前置检查（只读）
#
# 用途：在 Host A（ouo + SeaweedFS）上执行，判断能否用 native 方式
#       （systemd + 原生二进制）部署 SeaweedFS 4.x S3。
#
# 特性：
#   * 只读：不创建/修改/删除任何文件，不启停任何服务；
#   * 默认 dry-run（本脚本没有 --apply，永远只做检测）；
#   * 输出 SUPPORTED / UNSUPPORTED / MANUAL_REVIEW 及原因；
#   * 退出码：0 = SUPPORTED，2 = MANUAL_REVIEW，3 = UNSUPPORTED。
#
# 用法：
#   bash deploy/native/preflight.sh            # 只读检查
#   bash deploy/native/preflight.sh --help
#
# 可用环境变量（一般无需调整）：
#   MIN_FREE_GB=15      / 剩余空间建议下限（GB；SeaweedFS 10G + nginx 缓存 3G + 系统余量）
#   DISK_WARN_PCT=85    磁盘使用率告警线（%）
#   MIN_MEM_MB=1024     建议最小物理内存（MB，unit 里 MemoryMax=768M + GOMEMLIMIT=640MiB）
# ============================================================
set -euo pipefail

MIN_FREE_GB="${MIN_FREE_GB:-15}"
DISK_WARN_PCT="${DISK_WARN_PCT:-85}"
MIN_MEM_MB="${MIN_MEM_MB:-1024}"

SUPPORTED_LIST=()
MANUAL_LIST=()
UNSUPPORTED_LIST=()

usage() {
    cat <<'EOF'
用法: bash deploy/native/preflight.sh [--help]

只读探测本机是否满足「生产不使用 Docker」的 SeaweedFS 原生部署条件。
不写任何文件、不改变任何服务状态。

退出码:
  0  SUPPORTED      满足条件，可继续 install-weed.sh
  2  MANUAL_REVIEW  存在需要人工确认的项（不阻塞，但必须先看原因）
  3  UNSUPPORTED    存在硬性不满足项，禁止直接安装
EOF
}

ok()      { printf '[SUPPORTED]    %s\n' "$*"; SUPPORTED_LIST+=("$*"); }
manual()  { printf '[MANUAL_REVIEW] %s\n' "$*"; MANUAL_LIST+=("$*"); }
unsup()   { printf '[UNSUPPORTED]  %s\n' "$*"; UNSUPPORTED_LIST+=("$*"); }
info()    { printf '[INFO]         %s\n' "$*"; }
section() { printf '\n== %s ==\n' "$*"; }

has_cmd() { command -v "$1" >/dev/null 2>&1; }

while [[ $# -gt 0 ]]; do
    case "$1" in
        -h|--help) usage; exit 0 ;;
        --dry-run) shift ;;   # 默认行为（只读），显式传入也接受
        --apply)   printf '[ERROR] preflight.sh 只读，不支持 --apply\n' >&2; exit 2 ;;
        *) printf '[ERROR] 未知参数: %s（本脚本只读，无 --apply）\n' "$1" >&2; usage >&2; exit 2 ;;
    esac
done

printf 'yj-forum-ouo 生产原生部署前置检查（只读）\n'
printf '主机: %s  用户: %s  root: %s\n' "$(hostname 2>/dev/null || echo unknown)" "${USER:-unknown}" "$([[ ${EUID} -eq 0 ]] && echo yes || echo no)"

# ---------------------------------------------------------- #
# 1. 操作系统
# ---------------------------------------------------------- #
section '1. 操作系统'
OS_ID=''; OS_LIKE=''; OS_VER=''; OS_PRETTY=''
if [[ -r /etc/os-release ]]; then
    OS_ID=$(   . /etc/os-release; printf '%s' "${ID:-}" )
    OS_LIKE=$( . /etc/os-release; printf '%s' "${ID_LIKE:-}" )
    OS_VER=$(  . /etc/os-release; printf '%s' "${VERSION_ID:-}" )
    OS_PRETTY=$(. /etc/os-release; printf '%s' "${PRETTY_NAME:-}" )
    info "ID=${OS_ID:-?} ID_LIKE=${OS_LIKE:-?} VERSION_ID=${OS_VER:-?} (${OS_PRETTY:-?})"
else
    unsup '未找到 /etc/os-release，无法识别发行版'
fi

OS_FAMILY='unknown'
case " ${OS_ID} " in
    *' debian '*|*' ubuntu '*) OS_FAMILY='debian' ;;
esac
case " ${OS_ID} ${OS_LIKE} " in
    *rhel*|*centos*|*fedora*|*rocky*|*almalinux*|*openeuler*|*anolis*) OS_FAMILY='rhel' ;;
esac
case "$OS_FAMILY" in
    debian) ok "发行版属于 Debian/Ubuntu 系（ID=${OS_ID}），按 apt 流程部署" ;;
    rhel)   ok "发行版属于 RHEL 系（ID=${OS_ID}），按 dnf/yum 流程部署" ;;
    *)      manual "未识别的发行版（ID=${OS_ID:-?} ID_LIKE=${OS_LIKE:-?}）：SeaweedFS 为静态二进制、仍可能可用，但包管理与防火墙需人工确认" ;;
esac

# ---------------------------------------------------------- #
# 2. 架构 / glibc
# ---------------------------------------------------------- #
section '2. CPU 架构与 C 运行库'
MACHINE=$(uname -m 2>/dev/null || echo unknown)
info "uname -m = ${MACHINE}"
case "$MACHINE" in
    x86_64|amd64)  ok '架构 x86_64 → 使用 release 资产 linux_amd64.tar.gz' ;;
    aarch64|arm64) ok '架构 aarch64 → 使用 release 资产 linux_arm64.tar.gz' ;;
    armv7l|armv6l) manual "架构 ${MACHINE} → release 提供 linux_arm.tar.gz，但生产未验证，需人工确认" ;;
    *)             unsup "架构 ${MACHINE} 无官方 linux 构建" ;;
esac

if has_cmd getconf && GLIBC=$(getconf GNU_LIBC_VERSION 2>/dev/null); then
    GLIBC_VER=${GLIBC##* }
    info "glibc ${GLIBC_VER}"
    if [[ "$GLIBC_VER" =~ ^[0-9]+\.[0-9]+$ ]] && awk -v v="$GLIBC_VER" 'BEGIN{exit !(v+0 >= 2.17)}'; then
        ok "glibc ${GLIBC_VER} >= 2.17"
    else
        manual "glibc ${GLIBC_VER:-未知} 低于 2.17：weed 自身是静态二进制，但系统工具可能过旧"
    fi
elif has_cmd ldd && ldd --version 2>&1 | grep -qi musl; then
    info '检测到 musl libc（Alpine 等）：weed 为静态二进制可运行，但 systemd 部署通常不选 musl 发行版'
    manual 'musl libc：请人工确认 systemd/curl/tar 可用'
else
    info '未能读取 glibc 版本（非致命：weed 为静态二进制）'
fi

# ---------------------------------------------------------- #
# 3. systemd
# ---------------------------------------------------------- #
section '3. systemd'
if ! has_cmd systemctl; then
    unsup '未检测到 systemctl：本方案完全依赖 systemd unit，无法部署'
else
    SYSTEMD_VER=$(systemctl --version 2>/dev/null | head -n1 | awk '{print $2}' || true)
    info "systemctl --version = ${SYSTEMD_VER:-unknown}"
    PID1_COMM=$(ps -p 1 -o comm= 2>/dev/null || true)
    if [[ "$PID1_COMM" == 'systemd' ]]; then
        ok 'PID 1 为 systemd'
    else
        unsup "PID 1 为 '${PID1_COMM:-unknown}' 而非 systemd（容器/非 systemd 环境不能安装 unit）"
    fi
    if [[ "$SYSTEMD_VER" =~ ^[0-9]+$ ]] && (( SYSTEMD_VER < 232 )); then
        manual "systemd ${SYSTEMD_VER} < 232：MemoryMax/ProtectSystem 等加固项可能不被支持"
    elif [[ "$SYSTEMD_VER" =~ ^[0-9]+$ ]]; then
        ok "systemd ${SYSTEMD_VER} >= 232（支持 unit 加固项）"
    fi
fi

# ---------------------------------------------------------- #
# 4. 必需命令
# ---------------------------------------------------------- #
section '4. 必需命令'
for c in tar curl sha256sum install; do
    if has_cmd "$c"; then
        ok "命令可用: $c"
    else
        unsup "缺少命令: $c（install-weed.sh 依赖）"
    fi
done
has_cmd ss && ok '命令可用: ss（端口探测）' || manual '缺少 ss（iproute2），无法探测端口占用'

# ---------------------------------------------------------- #
# 5. 端口占用（ss -ltnp / -lunp）
# ---------------------------------------------------------- #
section '5. 端口占用（8333/9327/51820/80/443）'

# check_port <port> <tcp|udp> <label> <allow_regex> [conflict_level=unsup|manual] [allow_unknown=0|1]
check_port() {
    local port="$1" proto="$2" label="$3" allow_regex="$4" conflict_level="${5:-unsup}" allow_unknown="${6:-0}"
    local hits line procs local_addr host_part conflict_hits
    if ! has_cmd ss; then
        manual "无法检查端口 ${port}/${proto}（缺少 ss）"
        return 0
    fi
    if [[ "$proto" == 'tcp' ]]; then
        hits=$(ss -H -ltnp 2>/dev/null | awk -v p=":${port}" '$4 ~ p"$"' || true)
    else
        hits=$(ss -H -lunp 2>/dev/null | awk -v p=":${port}" '$4 ~ p"$"' || true)
    fi
    if [[ -z "$hits" ]]; then
        ok "端口 ${port}/${proto} 空闲（${label}）"
        return 0
    fi
    procs=$(printf '%s\n' "$hits" | sed -n 's/.*users:(("\([^"]*\)".*/\1/p' | sort -u | paste -sd, - || true)
    # 仅回环监听（如开发用 Docker 绑 127.0.0.1:8333）与生产绑定 10.8.0.1 不冲突
    conflict_hits=''
    while IFS= read -r line; do
        [[ -z "$line" ]] && continue
        local_addr=$(printf '%s' "$line" | awk '{print $4}')
        host_part=${local_addr%:*}
        host_part=${host_part#[}
        host_part=${host_part%]}
        case "$host_part" in
            127.*|::1|'') continue ;;
        esac
        conflict_hits+="${local_addr} "
    done <<< "$hits"
    info "端口 ${port}/${proto} 已被占用: $(printf '%s' "$hits" | awk '{print $4}' | paste -sd, -) 进程=${procs:-未知(需要 root 才能看到进程名)}"
    if [[ -z "$conflict_hits" ]]; then
        ok "端口 ${port}/${proto} 仅有回环监听（与 10.8.0.1 绑定不冲突）"
    elif [[ -n "$procs" ]] && printf '%s' "$procs" | grep -Eq "$allow_regex"; then
        ok "端口 ${port}/${proto} 由预期进程占用（${procs}）：属正常/升级场景"
    elif [[ "$allow_unknown" == '1' && -z "$procs" ]]; then
        ok "端口 ${port}/${proto} 已被占用且进程不可见（内核 WireGuard 套接字通常如此，视为正常）"
    elif [[ "$conflict_level" == 'manual' ]]; then
        manual "端口 ${port}/${proto} 在非回环地址被非预期进程占用（${conflict_hits}${procs:-进程未知}），需人工确认是否冲突"
    else
        unsup "端口 ${port}/${proto} 在非回环地址被非预期进程占用（${conflict_hits}${procs:-进程未知}），SeaweedFS 将无法监听"
    fi
}

# 8333/9327 只允许已有 weed；51820 允许内核 WireGuard；80/443 冲突不阻塞但需人工确认
check_port 8333 tcp  'S3 API'      '^(weed|seaweedfs)$'
check_port 9327 tcp  'S3 指标'      '^(weed|seaweedfs)$'
check_port 51820 udp 'WireGuard'   '^(wg|wireguard|systemd|kernel)$' manual 1
check_port 80 tcp   'HTTP/Nginx'   '^(nginx)$' manual
check_port 443 tcp  'HTTPS/Nginx'  '^(nginx)$' manual

# ---------------------------------------------------------- #
# 6. 磁盘
# ---------------------------------------------------------- #
section '6. 磁盘空间（df -h /）'
df -h / 2>/dev/null || manual 'df -h / 执行失败'
for p in / /var/lib/seaweedfs; do
    [[ -e "$p" ]] || { info "${p} 尚不存在（首次安装会创建）"; continue; }
    line=$(df -P -B1 "$p" 2>/dev/null | awk 'NR==2 {gsub("%","",$5); print $5, $4}' || true)
    if [[ -z "$line" ]]; then
        manual "无法读取 ${p} 的磁盘用量"
        continue
    fi
    use_pct=${line%% *}
    avail_bytes=${line##* }
    avail_gb=$(( avail_bytes / 1024 / 1024 / 1024 ))
    info "${p}: 使用率 ${use_pct}%，可用 ${avail_gb}GB"
    if (( avail_gb < MIN_FREE_GB )); then
        manual "${p} 可用空间 ${avail_gb}GB < 建议下限 ${MIN_FREE_GB}GB（S3 数据增长需预留）"
    elif (( use_pct >= DISK_WARN_PCT )); then
        manual "${p} 使用率 ${use_pct}% >= ${DISK_WARN_PCT}%，建议先清理或扩容"
    else
        ok "${p} 磁盘余量充足（可用 ${avail_gb}GB，使用率 ${use_pct}%）"
    fi
done

# ---------------------------------------------------------- #
# 7. 内存
# ---------------------------------------------------------- #
section '7. 内存（free -m）'
free -m 2>/dev/null || manual 'free -m 执行失败'
# 用 /proc/meminfo 避免 free 的本地化输出（中文 locale 下没有 "Mem:" 行）
MEM_TOTAL=$(awk '/^MemTotal:/{print int($2/1024)}' /proc/meminfo 2>/dev/null || true)
if [[ ! "$MEM_TOTAL" =~ ^[0-9]+$ ]]; then
    MEM_TOTAL=$(LC_ALL=C free -m 2>/dev/null | awk '/^Mem:/{print $2}' || true)
fi
MEM_AVAIL=$(awk '/^MemAvailable:/{print int($2/1024)}' /proc/meminfo 2>/dev/null || true)
if [[ "$MEM_TOTAL" =~ ^[0-9]+$ ]]; then
    info "物理内存 ${MEM_TOTAL}MB，当前可用 ${MEM_AVAIL:-?}MB（unit 设置 MemoryMax=1G）"
    if (( MEM_TOTAL < MIN_MEM_MB )); then
        manual "物理内存 ${MEM_TOTAL}MB < 建议下限 ${MIN_MEM_MB}MB（ouo + weed 同机）"
    else
        ok "物理内存 ${MEM_TOTAL}MB >= ${MIN_MEM_MB}MB"
    fi
else
    manual '无法读取物理内存大小'
fi

# ---------------------------------------------------------- #
# 8. SELinux / AppArmor
# ---------------------------------------------------------- #
section '8. SELinux / AppArmor'
SELINUX_MODE=''
if has_cmd getenforce; then
    SELINUX_MODE=$(getenforce 2>/dev/null || true)
elif [[ -r /sys/fs/selinux/enforce ]]; then
    [[ "$(cat /sys/fs/selinux/enforce 2>/dev/null)" == '1' ]] && SELINUX_MODE='Enforcing' || SELINUX_MODE='Permissive'
fi
case "$SELINUX_MODE" in
    Enforcing)
        manual 'SELinux=Enforcing：需为 /var/lib/seaweedfs 与 /etc/seaweedfs 配置 file context（semanage fcontext），或临时 setenforce 0 验证；见 native/README.md 排障'
        ;;
    Permissive) info 'SELinux=Permissive（不阻塞，但建议记录 AVC 日志）' ;;
    Disabled)   ok 'SELinux 已禁用' ;;
    '')         info '未检测到 SELinux' ;;
    *)          info "SELinux 状态: ${SELINUX_MODE}" ;;
esac

if [[ -d /sys/kernel/security/apparmor ]]; then
    if has_cmd aa-status && aa-status --enabled >/dev/null 2>&1; then
        info 'AppArmor 已启用（Ubuntu 默认）：无自定义 weed profile 时通常不影响；若启用了限制性 profile 需放行 /var/lib/seaweedfs 与 10.8.0.1:8333/9327'
        if aa-status 2>/dev/null | grep -qi 'seaweed\|/usr/local/bin/weed'; then
            manual '检测到针对 weed 的 AppArmor profile，请人工确认放行规则'
        fi
    else
        info 'AppArmor 目录存在但未启用'
    fi
else
    info '未检测到 AppArmor'
fi

# ---------------------------------------------------------- #
# 9. 既有 SeaweedFS / WireGuard
# ---------------------------------------------------------- #
section '9. 既有安装与 WireGuard'
if has_cmd systemctl && systemctl list-unit-files seaweedfs.service 2>/dev/null | grep -q '^seaweedfs\.service'; then
    SVC_STATE=$(systemctl is-active seaweedfs 2>/dev/null || true)
    SVC_FRAG=$(systemctl show -p FragmentPath --value seaweedfs 2>/dev/null || true)
    SVC_VER=''
    has_cmd weed && SVC_VER=$(weed version 2>/dev/null | head -n1 || true)
    info "已存在 seaweedfs.service（state=${SVC_STATE:-unknown}, unit=${SVC_FRAG:-?}, ${SVC_VER:-版本未知}）：install-weed.sh 将执行幂等升级/重装"
else
    info '未检测到 seaweedfs.service（全新安装）'
fi

if has_cmd wg; then
    ok 'wireguard-tools 已安装（wg 命令可用）'
else
    manual '未安装 wireguard-tools：S3 只绑定 10.8.0.1，必须先按 deploy/wireguard/README.md 建立 wg0'
fi
if has_cmd ip && ip link show wg0 >/dev/null 2>&1; then
    WG_ADDR=$(ip -o -4 addr show dev wg0 2>/dev/null | awk '{print $4}' | paste -sd, - || true)
    info "wg0 已存在，地址: ${WG_ADDR:-无 IPv4}"
    if [[ ",${WG_ADDR}," == *',10.8.0.1/'* ]]; then
        ok 'wg0 已配置 10.8.0.1'
    else
        manual 'wg0 存在但未配置 10.8.0.1（Host A 需要 10.8.0.1/24）'
    fi
else
    manual 'wg0 接口不存在：请先部署 WireGuard（deploy/wireguard/）'
fi

# ---------------------------------------------------------- #
# 结论
# ---------------------------------------------------------- #
printf '\n==================== 结论 ====================\n'
if (( ${#UNSUPPORTED_LIST[@]} > 0 )); then
    printf 'UNSUPPORTED\n'
    printf '  硬性不满足项（%d）：\n' "${#UNSUPPORTED_LIST[@]}"
    printf '    - %s\n' "${UNSUPPORTED_LIST[@]}"
    if (( ${#MANUAL_LIST[@]} > 0 )); then
        printf '  另需人工确认（%d）：\n' "${#MANUAL_LIST[@]}"
        printf '    - %s\n' "${MANUAL_LIST[@]}"
    fi
    exit 3
elif (( ${#MANUAL_LIST[@]} > 0 )); then
    printf 'MANUAL_REVIEW\n'
    printf '  需人工确认项（%d）：\n' "${#MANUAL_LIST[@]}"
    printf '    - %s\n' "${MANUAL_LIST[@]}"
    exit 2
else
    printf 'SUPPORTED\n'
    printf '  未发现阻塞项，可执行：sudo bash deploy/native/install-weed.sh --apply --version=4.47 --sha256=<校验值>\n'
    exit 0
fi
