#!/usr/bin/env bash
# ============================================================
# yj-ops 邮件通知（curl SMTP）
#
# 用法:
#   notify-mail.sh "<主题>" [正文文件]
#   printf '正文' | notify-mail.sh "<主题>"
#
# 配置: /etc/yj-ops/mail.env（可用 MAIL_ENV 覆盖），字段见 mail.env.example
#   SMTP_HOST / SMTP_PORT / SMTP_USER / SMTP_PASS
#   SMTP_TLS=implicit|starttls|none（默认 implicit，465 端口）
#   MAIL_FROM / MAIL_TO（多个收件人用逗号分隔）
#
# 特性:
#   * 缺 /etc/yj-ops/mail.env 或缺 curl 时：打印原因并退出 0（不影响巡检）；
#   * 同一主题在 NOTIFY_MIN_INTERVAL（默认 1800s）内只发一封，避免每 5 分钟轰炸；
#   * 状态目录可用 NOTIFY_STATE_DIR 覆盖（默认 /var/lib/yj-ops/notify）。
# ============================================================
set -euo pipefail

MAIL_ENV="${MAIL_ENV:-/etc/yj-ops/mail.env}"
SUBJECT="${1:-yj-ops 通知}"
BODY_FILE="${2:-}"

if [[ ! -f "$MAIL_ENV" ]]; then
    echo "[notify-mail] 未找到 ${MAIL_ENV}，跳过邮件通知"
    exit 0
fi
if ! command -v curl >/dev/null 2>&1; then
    echo '[notify-mail] 未安装 curl，跳过邮件通知'
    exit 0
fi

# shellcheck disable=SC1090
set -a; . "$MAIL_ENV"; set +a

SMTP_HOST="${SMTP_HOST:-}"
SMTP_PORT="${SMTP_PORT:-465}"
SMTP_USER="${SMTP_USER:-}"
SMTP_PASS="${SMTP_PASS:-}"
SMTP_TLS="${SMTP_TLS:-implicit}"
MAIL_FROM="${MAIL_FROM:-}"
MAIL_TO="${MAIL_TO:-}"

if [[ -z "$SMTP_HOST" || -z "$MAIL_FROM" || -z "$MAIL_TO" ]]; then
    echo '[notify-mail] 配置不完整（需要 SMTP_HOST / MAIL_FROM / MAIL_TO），跳过邮件通知'
    exit 0
fi

# ---- 正文 --------------------------------------------------------
BODY=''
if [[ -n "$BODY_FILE" ]]; then
    if [[ ! -r "$BODY_FILE" ]]; then
        echo "[notify-mail] 正文文件不存在: ${BODY_FILE}，跳过"
        exit 0
    fi
    BODY=$(cat "$BODY_FILE")
elif [[ ! -t 0 ]]; then
    BODY=$(cat)
fi
[[ -n "$BODY" ]] || BODY="$(date '+%F %T') 主机 $(hostname) 触发 yj-ops 通知"

# ---- 限流：同主题 30 分钟内只发一次 ---------------------------------
STATE_DIR="${NOTIFY_STATE_DIR:-/var/lib/yj-ops/notify}"
MIN_INTERVAL="${NOTIFY_MIN_INTERVAL:-1800}"
KEY=$(printf '%s' "$SUBJECT" | md5sum | awk '{print $1}')
STATE_FILE="${STATE_DIR}/${KEY}.last"
if mkdir -p "$STATE_DIR" 2>/dev/null; then
    if [[ -f "$STATE_FILE" ]]; then
        now=$(date +%s)
        last=$(stat -c %Y "$STATE_FILE" 2>/dev/null || echo 0)
        if (( now - last < MIN_INTERVAL )); then
            echo "[notify-mail] 同一主题 $(( (MIN_INTERVAL - (now - last)) / 60 )) 分钟内已发送，跳过"
            exit 0
        fi
    fi
fi

# ---- 组装邮件 ----------------------------------------------------
FROM_ADDR="${MAIL_FROM_ADDR:-}"
if [[ -z "$FROM_ADDR" ]]; then
    FROM_ADDR=$(printf '%s' "$MAIL_FROM" | sed -n 's/.*<\([^>]*\)>.*/\1/p')
    [[ -n "$FROM_ADDR" ]] || FROM_ADDR="$MAIL_FROM"
fi

if LC_ALL=C printf '%s' "$SUBJECT" | grep -q '[^ -~]'; then
    SUBJECT_HEADER="=?UTF-8?B?$(printf '%s' "$SUBJECT" | base64 | tr -d '\n')?="
else
    SUBJECT_HEADER="$SUBJECT"
fi

MESSAGE=$(printf 'From: %s\r\nTo: %s\r\nSubject: %s\r\nDate: %s\r\nMIME-Version: 1.0\r\nContent-Type: text/plain; charset=UTF-8\r\nContent-Transfer-Encoding: 8bit\r\n\r\n%s\r\n' \
    "$MAIL_FROM" "$MAIL_TO" "$SUBJECT_HEADER" "$(date -R)" "$BODY")

# ---- 发送 --------------------------------------------------------
case "$SMTP_TLS" in
    starttls) SCHEME='smtp'; TLS_ARGS=(--ssl-reqd) ;;
    none)     SCHEME='smtp'; TLS_ARGS=() ;;
    *)        SCHEME='smtps'; TLS_ARGS=() ;;
esac

RCPT_ARGS=()
for addr in $(printf '%s' "$MAIL_TO" | tr ',' ' '); do
    [[ -n "$addr" ]] && RCPT_ARGS+=(--mail-rcpt "$addr")
done

AUTH_ARGS=()
[[ -n "$SMTP_USER" ]] && AUTH_ARGS=(--user "${SMTP_USER}:${SMTP_PASS}")

if printf '%s' "$MESSAGE" | curl -sS --max-time 30 --connect-timeout 10 \
    --url "${SCHEME}://${SMTP_HOST}:${SMTP_PORT}" \
    "${TLS_ARGS[@]}" "${AUTH_ARGS[@]}" \
    --mail-from "$FROM_ADDR" "${RCPT_ARGS[@]}" --upload-file - ; then
    echo "[notify-mail] 已发送: ${SUBJECT}"
    [[ -d "$STATE_DIR" ]] && touch "$STATE_FILE" 2>/dev/null || true
else
    echo "[notify-mail] 发送失败（${SMTP_HOST}:${SMTP_PORT}）: ${SUBJECT}" >&2
    exit 1
fi
