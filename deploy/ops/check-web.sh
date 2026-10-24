#!/usr/bin/env bash
# ============================================================
# yj-ops：前端（Next.js standalone）静态资源健康巡检
#
# 检查对象：首页 HTML 自身，以及它引用的 /_next/static/* 与 public/ 资源。
# 背景（真实事故）：.next/standalone 里漏复制 .next/static 与 public 时，
#   首页仍会 200（预渲染 HTML 在 server 包里），但所有 JS/CSS/图片全部 404 —— 页面白屏。
#   仅看首页状态码的巡检抓不到这类故障，所以必须校验静态资源。
#
# 退出码：0 正常；1 异常（会尝试发邮件）。
# 可用环境变量：
#   WEB_BASE=http://127.0.0.1:3000   前端根地址（巡检本机服务，不经 nginx）
#   CHECK_TIMEOUT=8                  单请求超时（秒）
#   WEB_SAMPLES=6                    抽查的 /_next/static/* 资源个数
#   WEB_PUBLIC_PATHS=/manifest.json,/assets/img/favicon.png   public/ 抽查路径（逗号分隔）
# ============================================================
set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
WEB_BASE="${WEB_BASE:-http://127.0.0.1:3000}"
TIMEOUT="${CHECK_TIMEOUT:-8}"
SAMPLES="${WEB_SAMPLES:-6}"
PUBLIC_PATHS="${WEB_PUBLIC_PATHS:-/manifest.json,/assets/img/favicon.png}"

fail() { errors+=("$1"); echo "[FAIL] $1"; }
ok()   { echo "[OK]   $1"; }

http_code() {
    curl -sS -o /dev/null -w '%{http_code}' --max-time "$TIMEOUT" "$1" 2>/dev/null || true
}

declare -a errors=()

# 0. 服务存活
code=$(http_code "${WEB_BASE}/")
if [[ "${code}" != '200' ]]; then
    fail "前端首页 ${WEB_BASE}/ 不可用（HTTP ${code:-无响应}）"
    if [[ -x "${SCRIPT_DIR}/notify-mail.sh" ]]; then
        printf '%s\n主机: %s\n时间: %s\n' "$(printf '%s\n' "${errors[@]}")" "$(hostname)" "$(date '+%F %T')" \
            | "${SCRIPT_DIR}/notify-mail.sh" "[yj-ops][CRIT] 前端不可用 $(hostname)" || true
    fi
    exit 1
fi
ok "首页 ${WEB_BASE}/ → HTTP 200"

# 1. 抽取首页引用的静态资源（HTML 与 RSC 内联数据里可能有转义，排除反斜线）
html_file=$(mktemp)
trap 'rm -f "$html_file"' EXIT
curl -sS --max-time "$TIMEOUT" "${WEB_BASE}/" -o "$html_file" || true
mapfile -t refs < <(grep -oE '/_next/static/[A-Za-z0-9._/-]+' "$html_file" 2>/dev/null | sort -u | head -n "$SAMPLES" || true)

if (( ${#refs[@]} == 0 )); then
    fail '首页未引用任何 /_next/static/ 资源（构建产物异常？）'
else
    for ref in "${refs[@]}"; do
        code=$(http_code "${WEB_BASE}${ref}")
        if [[ "$code" == '200' ]]; then
            ok "静态资源 ${ref} → HTTP 200"
        else
            fail "静态资源 ${ref} → HTTP ${code:-无响应}（检查 .next/standalone/.next/static 是否存在）"
        fi
    done
fi

# 2. public/ 资源抽查（漏复制 public 时这些会返回 404 HTML）
IFS=',' read -r -a public_list <<< "$PUBLIC_PATHS"
for path in "${public_list[@]}"; do
    path=$(printf '%s' "$path" | tr -d '[:space:]')
    [[ -n "$path" ]] || continue
    code=$(http_code "${WEB_BASE}${path}")
    if [[ "$code" == '200' ]]; then
        ok "public ${path} → HTTP 200"
    else
        fail "public ${path} → HTTP ${code:-无响应}（检查 .next/standalone/public 是否存在）"
    fi
done

if (( ${#errors[@]} > 0 )); then
    cat >&2 <<'TIP'
[yj-ops] 修复提示：
  cd /opt/yj-forum/web && git pull && API_TARGET=http://127.0.0.1:8090 pnpm build && systemctl restart yj-web
  （pnpm build 的 postbuild 会自动执行 scripts/prepare-standalone.mjs 把 static/public 复制进 standalone）
TIP
    if [[ -x "${SCRIPT_DIR}/notify-mail.sh" ]]; then
        printf '%s\n主机: %s\n时间: %s\n' "$(printf '%s\n' "${errors[@]}")" "$(hostname)" "$(date '+%F %T')" \
            | "${SCRIPT_DIR}/notify-mail.sh" "[yj-ops][CRIT] 前端静态资源异常 $(hostname)" || true
    fi
    exit 1
fi

exit 0
