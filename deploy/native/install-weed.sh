#!/usr/bin/env bash
# ============================================================
# yj-forum-ouo 生产原生部署 —— 安装 / 升级 SeaweedFS（weed）
#
# 默认 dry-run：只打印将要执行的命令，不改动系统。
# 必须显式 --apply 才会真正安装（需要 root）。
#
# 安装内容：
#   * 系统用户/组          seaweedfs（nologin）
#   * 数据目录             /var/lib/seaweedfs/data（0750，属主 seaweedfs）
#   * 配置目录             /etc/seaweedfs（0750，root:seaweedfs）
#   * 二进制               /opt/seaweedfs/<version>/weed，软链 /usr/local/bin/weed
#   * systemd unit         /etc/systemd/system/seaweedfs.service
#   * S3 配置              /etc/seaweedfs/s3.json（缺失时从 s3.json.example 生成）
#   * bucket               yj-forum（经 weed shell 幂等创建）
#   * 服务                 enable + start（绑定 10.8.0.1:8333 / 指标 9327）
#
# 用法：
#   sudo bash deploy/native/install-weed.sh \
#       --apply --version=4.47 --sha256=<64位sha256>
#
# 参数：
#   --dry-run                默认；只打印计划
#   --apply                  真正执行（需要 root）
#   --version=<ver>          SeaweedFS 版本（默认 4.47，对应 GitHub release tag）
#   --sha256=<hex>           安装包 SHA256；不传则尝试下载官方 <url>.sha256，
#                            拿不到就报错（官方 release 目前只提供 .md5）
#   --archive=<path>         使用本地 tar.gz（离线/内网）；仍必须传 --sha256
#   --url=<url>              覆盖下载地址（默认 GitHub release linux_<arch>.tar.gz）
#   --bucket=<name>          S3 bucket（默认 yj-forum）
#   --bind-ip=<ip>           监听地址（默认 10.8.0.1，WireGuard Host A）
#   --master=<host:port>     weed shell 连接 master（默认 <bind-ip>:9333）
#   --allow-placeholder-s3   s3.json 仍含 <CHANGE_ME_*> 时也继续（不建议）
#   --skip-wg-check          跳过 wg0/10.8.0.1 地址检查（仅用于预装二进制）
#   -h, --help               显示帮助
#
# 幂等：重复执行 = 升级/修复；不改写已存在的 s3.json；已存在的 bucket 不会重建。
# ============================================================
set -euo pipefail
umask 022

SVC_NAME='seaweedfs'
SVC_USER='seaweedfs'
PREFIX='/opt/seaweedfs'
UNIT_PATH="/etc/systemd/system/${SVC_NAME}.service"
CONF_DIR='/etc/seaweedfs'
STATE_DIR='/var/lib/seaweedfs'
DATA_DIR='/var/lib/seaweedfs/data'
BIN_LINK='/usr/local/bin/weed'
REPO='seaweedfs/seaweedfs'
SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)

DRY_RUN=1
VERSION='4.47'
SHA256=''
ARCHIVE=''
URL_OVERRIDE=''
BUCKET='yj-forum'
BIND_IP='10.8.0.1'
MASTER_ADDR=''
ALLOW_PLACEHOLDER_S3=0
SKIP_WG_CHECK=0

STAGE_DIR=''
WEED_BIN=''
DOWNLOAD_URL=''

usage() {
    cat <<'EOF'
用法: bash deploy/native/install-weed.sh [选项]

默认 dry-run（只打印计划）；必须显式 --apply 才会修改系统（需 root）。

选项:
  --dry-run                只打印计划（默认）
  --apply                  真正执行安装/升级
  --version=<ver>          SeaweedFS 版本，默认 4.47（即 GitHub release tag）
  --sha256=<hex>           安装包 SHA256；不传则尝试官方 <url>.sha256，
                           拿不到就报错（官方 release 目前只提供 .md5）
  --archive=<path>         使用本地 tar.gz（离线/内网），仍必须配 --sha256
  --url=<url>              覆盖下载地址
  --bucket=<name>          S3 bucket，默认 yj-forum
  --bind-ip=<ip>           监听地址，默认 10.8.0.1（WireGuard Host A）
  --master=<host:port>     weed shell 的 master 地址，默认 <bind-ip>:9333
  --allow-placeholder-s3   s3.json 仍含 <CHANGE_ME_*> 时也继续（不建议）
  --skip-wg-check          跳过 wg0 / 10.8.0.1 检查（仅预装二进制时使用）
  -h, --help               显示本帮助

示例:
  bash deploy/native/install-weed.sh                       # dry-run 看计划
  sudo bash deploy/native/install-weed.sh --apply --version=4.47 --sha256=<hex>
EOF
}

log()  { printf '[%s] %s\n' "$1" "$2"; }
info() { log 'INFO' "$*"; }
warn() { log 'WARN' "$*"; }
plan() { printf '[plan] %s\n' "$*"; }
die()  { printf '[ERROR] %s\n' "$*" >&2; exit 1; }

cleanup() {
    if [[ -n "$STAGE_DIR" && -d "$STAGE_DIR" ]]; then
        rm -rf "$STAGE_DIR"
    fi
}
trap cleanup EXIT

while [[ $# -gt 0 ]]; do
    case "$1" in
        --dry-run)               DRY_RUN=1; shift ;;
        --apply)                 DRY_RUN=0; shift ;;
        --version=*)             VERSION=${1#*=}; shift ;;
        --version)               VERSION=${2:?'--version 需要值，如 --version=4.47'}; shift 2 ;;
        --sha256=*)              SHA256=${1#*=}; shift ;;
        --sha256)                SHA256=${2:?'--sha256 需要值'}; shift 2 ;;
        --archive=*)             ARCHIVE=${1#*=}; shift ;;
        --archive)               ARCHIVE=${2:?'--archive 需要路径'}; shift 2 ;;
        --url=*)                 URL_OVERRIDE=${1#*=}; shift ;;
        --url)                   URL_OVERRIDE=${2:?'--url 需要值'}; shift 2 ;;
        --bucket=*)              BUCKET=${1#*=}; shift ;;
        --bucket)                BUCKET=${2:?'--bucket 需要值'}; shift 2 ;;
        --bind-ip=*)             BIND_IP=${1#*=}; shift ;;
        --bind-ip)               BIND_IP=${2:?'--bind-ip 需要值'}; shift 2 ;;
        --master=*)              MASTER_ADDR=${1#*=}; shift ;;
        --master)                MASTER_ADDR=${2:?'--master 需要值'}; shift 2 ;;
        --allow-placeholder-s3)  ALLOW_PLACEHOLDER_S3=1; shift ;;
        --skip-wg-check)         SKIP_WG_CHECK=1; shift ;;
        -h|--help)               usage; exit 0 ;;
        *) die "未知参数: $1（--help 查看用法）" ;;
    esac
done

[[ "$VERSION" =~ ^[0-9][0-9A-Za-z._-]*$ ]] || die "非法版本号: $VERSION"
[[ "$BUCKET" =~ ^[a-z0-9][a-z0-9.-]{1,61}[a-z0-9]$ ]] || die "非法 bucket 名: $BUCKET"
[[ "$BIND_IP" =~ ^[0-9.]+$ ]] || die "--bind-ip 目前只支持 IPv4: $BIND_IP"
[[ -n "$MASTER_ADDR" ]] || MASTER_ADDR="${BIND_IP}:9333"

for f in seaweedfs.service s3.json.example; do
    [[ -f "${SCRIPT_DIR}/${f}" ]] || die "同目录缺少 ${f}（本脚本需与 unit/示例配置一起使用）"
done

if (( ! DRY_RUN )); then
    (( EUID == 0 )) || die '--apply 需要 root 权限，请使用 sudo 执行'
fi

# ---- 平台识别 -------------------------------------------------
[[ "$(uname -s)" == 'Linux' ]] || die '仅支持 Linux'
case "$(uname -m)" in
    x86_64|amd64)  ARCH='amd64' ;;
    aarch64|arm64) ARCH='arm64' ;;
    armv7l|armv6l) ARCH='arm' ;;
    *) die "不支持的架构: $(uname -m)" ;;
esac

if [[ -n "$URL_OVERRIDE" ]]; then
    DOWNLOAD_URL="$URL_OVERRIDE"
else
    DOWNLOAD_URL="https://github.com/${REPO}/releases/download/${VERSION}/linux_${ARCH}.tar.gz"
fi

if [[ -n "$SHA256" ]]; then
    [[ "$SHA256" =~ ^[0-9a-fA-F]{64}$ ]] || die '--sha256 必须是 64 位十六进制字符串'
fi
if [[ -n "$ARCHIVE" ]]; then
    [[ -r "$ARCHIVE" ]] || die "--archive 不存在或不可读: ${ARCHIVE}"
    [[ -n "$SHA256" ]] || die '使用 --archive（离线/内网）时必须同时提供 --sha256=<64位hex>'
fi

printf '=== SeaweedFS 原生安装（%s）===\n' "$([[ $DRY_RUN -eq 1 ]] && echo 'dry-run，不修改系统' || echo 'APPLY，将修改系统')"
printf '  版本: %s   架构: linux_%s\n' "$VERSION" "$ARCH"
printf '  下载: %s\n' "${ARCHIVE:-$DOWNLOAD_URL}"
printf '  数据: %s   配置: %s/s3.json\n' "$DATA_DIR" "$CONF_DIR"
printf '  监听: %s:8333（S3）/ %s:9327（指标）\n' "$BIND_IP" "$BIND_IP"
printf '  bucket: %s\n' "$BUCKET"

# ---- 1. WireGuard 前置（服务 unit Requires=wg-quick@wg0.service）----
printf '\n--- 1/9 检查 WireGuard 与监听地址 ---\n'
if (( SKIP_WG_CHECK )); then
    warn '已指定 --skip-wg-check，跳过 10.8.0.1 / wg-quick@wg0 检查（服务可能无法启动）'
else
    if [[ -n "$(ip -o -4 addr show 2>/dev/null | awk -v ip="${BIND_IP}" '$4 ~ ("^" ip "/")' || true)" ]]; then
        info "主机已配置 ${BIND_IP}"
    elif (( DRY_RUN )); then
        warn "当前主机未找到 ${BIND_IP}；--apply 时会在此中止（请先部署 deploy/wireguard/）"
    else
        die "主机未配置 ${BIND_IP}；请先按 deploy/wireguard/README.md 建立 wg0（Host A = 10.8.0.1）"
    fi
    if systemctl cat wg-quick@wg0.service >/dev/null 2>&1; then
        info 'wg-quick@wg0.service 存在'
    elif (( DRY_RUN )); then
        warn '未找到 wg-quick@wg0.service；--apply 时启动会失败（unit 里 Requires=wg-quick@wg0.service）'
    else
        die '未找到 wg-quick@wg0.service；请先按 deploy/wireguard/README.md 部署 WireGuard'
    fi
fi

# ---- 2. 系统用户 -------------------------------------------------
printf '\n--- 2/9 系统用户 %s ---\n' "$SVC_USER"
if id -u "$SVC_USER" >/dev/null 2>&1; then
    info "用户 ${SVC_USER} 已存在（uid=$(id -u "$SVC_USER")）"
else
    NOLOGIN='/usr/sbin/nologin'
    [[ -x "$NOLOGIN" ]] || NOLOGIN='/sbin/nologin'
    [[ -x "$NOLOGIN" ]] || NOLOGIN='/bin/false'
    if (( DRY_RUN )); then
        plan "useradd --system --home-dir ${STATE_DIR} --shell ${NOLOGIN} --no-create-home ${SVC_USER}"
    else
        useradd --system --home-dir "$STATE_DIR" --shell "$NOLOGIN" --no-create-home "$SVC_USER"
        info "已创建系统用户 ${SVC_USER}"
    fi
fi

# ---- 3. 目录 -----------------------------------------------------
printf '\n--- 3/9 目录 ---\n'
if (( DRY_RUN )); then
    plan "install -d -m 0750 -o ${SVC_USER} -g ${SVC_USER} ${STATE_DIR} ${DATA_DIR}"
    plan "install -d -m 0750 -o root -g ${SVC_USER} ${CONF_DIR}"
    plan "install -d -m 0755 -o root -g root ${PREFIX}/${VERSION}"
else
    install -d -m 0750 -o "$SVC_USER" -g "$SVC_USER" "$STATE_DIR" "$DATA_DIR"
    install -d -m 0750 -o root -g "$SVC_USER" "$CONF_DIR"
    install -d -m 0755 -o root -g root "${PREFIX}/${VERSION}"
    info "目录就绪: ${DATA_DIR} / ${CONF_DIR} / ${PREFIX}/${VERSION}"
fi

# ---- 4. 下载 + 校验 ----------------------------------------------
printf '\n--- 4/9 下载与 SHA256 校验 ---\n'
if (( DRY_RUN )); then
    if [[ -n "$ARCHIVE" ]]; then
        plan "使用本地归档 ${ARCHIVE}（要求 --sha256）"
    else
        plan "curl -fL --retry 3 -o <tmp>/linux_${ARCH}.tar.gz ${DOWNLOAD_URL}"
    fi
    if [[ -n "$SHA256" ]]; then
        plan "sha256sum -c  （期望 ${SHA256}）"
    else
        plan "尝试下载 ${DOWNLOAD_URL}.sha256；官方 release 通常只有 .md5，此时会报错并要求显式传 --sha256"
    fi
else
    STAGE_DIR=$(mktemp -d /tmp/weed-install.XXXXXX)
    TARBALL="${STAGE_DIR}/linux_${ARCH}.tar.gz"
    if [[ -n "$ARCHIVE" ]]; then
        [[ -r "$ARCHIVE" ]] || die "--archive 不存在或不可读: ${ARCHIVE}"
        cp -f "$ARCHIVE" "$TARBALL"
        info "已复制本地归档: ${ARCHIVE}"
    else
        info "下载 ${DOWNLOAD_URL}"
        curl -fL --retry 3 --retry-delay 2 --connect-timeout 15 --progress-bar -o "$TARBALL" "$DOWNLOAD_URL" \
            || die "下载失败: ${DOWNLOAD_URL}"
    fi

    if [[ -z "$SHA256" ]]; then
        SHA_URL="${DOWNLOAD_URL}.sha256"
        SHA_FILE="${STAGE_DIR}/archive.sha256"
        info "未传 --sha256，尝试官方校验文件 ${SHA_URL}"
        if curl -fsSL --connect-timeout 10 --max-time 30 -o "$SHA_FILE" "$SHA_URL" 2>/dev/null; then
            SHA256=$(awk 'NF>=1 {print $1; exit}' "$SHA_FILE" || true)
            [[ "$SHA256" =~ ^[0-9a-fA-F]{64}$ ]] || die "官方校验文件格式异常: ${SHA_URL}"
            info "已获取官方 SHA256: ${SHA256}"
        else
            die "无法获取官方 SHA256（${SHA_URL}）。官方 release 目前只提供 .md5；请在可信环境核对后显式传 --sha256=<64位hex>"
        fi
    fi

    printf '%s  %s\n' "${SHA256,,}" "$TARBALL" | sha256sum -c - >/dev/null \
        || die "SHA256 校验失败（期望 ${SHA256}）"
    info "SHA256 校验通过"
fi

# ---- 5. 解压 / 安装二进制 ---------------------------------------
printf '\n--- 5/9 安装二进制 ---\n'
if (( DRY_RUN )); then
    plan "tar -xzf <archive> -C <tmp>/extract && 定位 weed"
    plan "install -m 0755 <weed> ${PREFIX}/${VERSION}/weed"
    plan "ln -sfn ${PREFIX}/${VERSION}/weed ${BIN_LINK}"
else
    EXTRACT_DIR="${STAGE_DIR}/extract"
    mkdir -p "$EXTRACT_DIR"
    tar -xzf "$TARBALL" -C "$EXTRACT_DIR"
    WEED_BIN=$(find "$EXTRACT_DIR" -type f -name weed -perm -u+x -print -quit || true)
    [[ -n "$WEED_BIN" ]] || WEED_BIN=$(find "$EXTRACT_DIR" -type f -name weed -print -quit || true)
    [[ -n "$WEED_BIN" ]] || die '归档中未找到 weed 可执行文件'
    chmod 0755 "$WEED_BIN"
    if ! "$WEED_BIN" version >/dev/null 2>&1; then
        warn 'weed version 执行失败（继续安装；SHA256 已校验，若无法启动请检查架构）'
    fi
    install -m 0755 -o root -g root "$WEED_BIN" "${PREFIX}/${VERSION}/weed"
    ln -sfn "${PREFIX}/${VERSION}/weed" "$BIN_LINK"
    info "已安装 ${PREFIX}/${VERSION}/weed → ${BIN_LINK}"
    "$BIN_LINK" version 2>/dev/null | head -n1 | sed 's/^/  weed version: /' || true
fi

# ---- 6. systemd unit --------------------------------------------
printf '\n--- 6/9 systemd unit ---\n'
if (( DRY_RUN )); then
    plan "install -m 0644 ${SCRIPT_DIR}/seaweedfs.service ${UNIT_PATH}"
else
    install -m 0644 -o root -g root "${SCRIPT_DIR}/seaweedfs.service" "$UNIT_PATH"
    info "已写入 ${UNIT_PATH}"
    systemctl daemon-reload
fi

# ---- 7. s3.json --------------------------------------------------
printf '\n--- 7/9 S3 凭据配置 ---\n'
S3_JSON="${CONF_DIR}/s3.json"
if [[ -f "$S3_JSON" ]]; then
    info "已存在 ${S3_JSON}（不会被覆盖）"
    if grep -q '<CHANGE_ME' "$S3_JSON"; then
        if (( ALLOW_PLACEHOLDER_S3 )); then
            warn "${S3_JSON} 仍含 <CHANGE_ME_*> 占位符（已指定 --allow-placeholder-s3，继续）"
        elif (( DRY_RUN )); then
            warn "${S3_JSON} 仍含占位符；--apply 会在此中止，请先改强随机凭据"
        else
            die "${S3_JSON} 仍含 <CHANGE_ME_*> 占位符，请先编辑为强随机 accessKey/secretKey 再重跑"
        fi
    fi
    if (( ! DRY_RUN )); then
        chown root:"$SVC_USER" "$S3_JSON"
        chmod 0640 "$S3_JSON"
    fi
else
    if (( DRY_RUN )); then
        plan "install -m 0640 -g ${SVC_USER} ${SCRIPT_DIR}/s3.json.example ${S3_JSON}"
        warn "首次安装会生成占位符配置并中止；需改为强随机凭据后重跑"
    else
        install -m 0640 -o root -g "$SVC_USER" "${SCRIPT_DIR}/s3.json.example" "$S3_JSON"
        if (( ALLOW_PLACEHOLDER_S3 )); then
            warn "已生成 ${S3_JSON}，仍含占位符（--allow-placeholder-s3）"
        else
            warn "已生成 ${S3_JSON}（占位符）"
            printf '\n请先编辑 %s，把 <CHANGE_ME_*> 改成强随机值，然后重跑本脚本：\n' "$S3_JSON"
            printf '  sudoedit %s\n' "$S3_JSON"
            printf '  sudo bash %s --apply --version=%s --sha256=%s\n' "$0" "$VERSION" "${SHA256:-<hex>}"
            exit 1
        fi
    fi
fi

# ---- 8. enable + start ------------------------------------------
printf '\n--- 8/9 启动服务 ---\n'
if (( DRY_RUN )); then
    plan "systemctl enable ${SVC_NAME}"
    plan "systemctl restart ${SVC_NAME}"
    plan "等待 http://${BIND_IP}:8333/ 返回 403/200"
else
    systemctl enable "$SVC_NAME" >/dev/null
    if ! systemctl restart "$SVC_NAME"; then
        systemctl status --no-pager -l "$SVC_NAME" || true
        journalctl -u "$SVC_NAME" -n 60 --no-pager || true
        die "${SVC_NAME} 启动失败（常见原因：s3.json 非法、10.8.0.1 未配置、端口被占）"
    fi
    deadline=$((SECONDS + 60))
    ready=0
    while (( SECONDS < deadline )); do
        code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 2 "http://${BIND_IP}:8333/" || true)
        if [[ "$code" == '403' || "$code" == '200' ]]; then
            info "S3 已就绪（HTTP ${code}，未签名请求返回 403 属正常）"
            ready=1
            break
        fi
        sleep 1
    done
    if (( ready == 0 )); then
        systemctl status --no-pager -l "$SVC_NAME" || true
        journalctl -u "$SVC_NAME" -n 60 --no-pager || true
        die "等待 S3 就绪超时（${BIND_IP}:8333）"
    fi
fi

# ---- 9. bucket ---------------------------------------------------
printf '\n--- 9/9 bucket %s ---\n' "$BUCKET"
bucket_exists() {
    # s3.bucket.list 每行形如：  yj-forum<TAB>size:392<TAB>...
    printf 's3.bucket.list\n' | timeout 20 "$BIN_LINK" shell -master="$MASTER_ADDR" 2>/dev/null \
        | awk -v b="$BUCKET" '$1 == b { found = 1 } END { exit(found ? 0 : 1) }'
}

if (( DRY_RUN )); then
    plan "weed shell -master=${MASTER_ADDR}: s3.bucket.list，不存在则 s3.bucket.create -name ${BUCKET}"
else
    if bucket_exists; then
        info "bucket ${BUCKET} 已存在"
    else
        info "创建 bucket ${BUCKET}"
        printf 's3.bucket.create -name %s\n' "$BUCKET" | timeout 20 "$BIN_LINK" shell -master="$MASTER_ADDR" \
            || die 's3.bucket.create 执行失败'
        bucket_exists || die "bucket ${BUCKET} 创建后仍未列出，请检查 weed shell 输出"
        info "bucket ${BUCKET} 已创建"
    fi
fi

# ---- 完成 --------------------------------------------------------
printf '\n=== %s ===\n' "$([[ $DRY_RUN -eq 1 ]] && echo 'dry-run 完成（未修改系统）' || echo '安装完成')"
cat <<EOF
  服务状态 : systemctl status ${SVC_NAME}
  配置     : ${S3_JSON}
  数据目录 : ${DATA_DIR}
  S3 端点  : http://${BIND_IP}:8333   （仅 WireGuard 内网，公网不开放）
  指标     : http://${BIND_IP}:9327/metrics
  日志     : journalctl -u ${SVC_NAME} -f

  下一步：
  1) 在 ouo/admin 的 .env 配置 S3_ENABLED=true / S3_ENDPOINT=http://${BIND_IP}:8333 / S3_BUCKET=${BUCKET}
     以及 ${S3_JSON} 中对应 identity 的 accessKey/secretKey；
  2) 重启 yj-forum / yj-admin 服务；
  3) 按 deploy/native/README.md 的验收命令检查上传与读取。
EOF
