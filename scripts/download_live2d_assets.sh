#!/usr/bin/env bash
# ---------------------------------------------------------------
# 将 Live2D / WIKI 相关静态资源从原 CDN 下载到项目本地目录，
# 使所有资源走同站 /static/... 路径，避免跨域依赖。
#
# 在服务器 ~/forum-new 下执行：
#   bash scripts/download_live2d_assets.sh
#
# 如已下载再次执行会自动跳过（用 -f 强制重下）。
# ---------------------------------------------------------------
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT"

LIVE2D_DIR="static/live2d"
GIF_DIR="static/live2d/gif"
JS_DIR="static/live2d/js"
WIKI_IMG_DIR="static/img/wiki"
mkdir -p "$LIVE2D_DIR" "$GIF_DIR" "$JS_DIR" "$WIKI_IMG_DIR"

CDN_ASSETS="https://assets.crazying-dev.top/text/one"
CDN_IMG="https://img.crazying-dev.top/text/one"

FORCE=0
[[ "${1:-}" == "-f" ]] && FORCE=1

need_download() {
  local f="$1"
  [[ $FORCE -eq 1 ]] && return 0
  [[ -f "$f" ]] && return 1
  return 0
}

download() {
  local url="$1" dst="$2"
  if need_download "$dst"; then
    echo "⬇  $(basename "$dst")"
    curl -fSL --retry 3 --connect-timeout 15 -o "$dst" "$url"
  else
    echo "⏭  $(basename "$dst") 已存在，跳过"
  fi
}

echo "--- Live2D 模型 ---"
download "$CDN_ASSETS/Live2D/HEI.lpk"            "$LIVE2D_DIR/HEI.lpk"

echo "--- Live2D 引擎 JS ---"
download "$CDN_ASSETS/JS/Live2DLPK.js"            "$JS_DIR/Live2DLPK.js"

echo "--- Live2D 动作 GIF (5张) ---"
download "$CDN_ASSETS/Live2D/GIF/待机.gif"        "$GIF_DIR/待机.gif"
download "$CDN_ASSETS/Live2D/GIF/嘿咻.gif"        "$GIF_DIR/嘿咻.gif"
download "$CDN_ASSETS/Live2D/GIF/惊醒.gif"        "$GIF_DIR/惊醒.gif"
download "$CDN_ASSETS/Live2D/GIF/起跳.gif"        "$GIF_DIR/起跳.gif"
download "$CDN_ASSETS/Live2D/GIF/铁片.gif"        "$GIF_DIR/铁片.gif"

echo "--- WIKI 封面图 (2张) ---"
download "$CDN_IMG/714aed796653e9135b7c24cebe3960c712fa808156cc-hJpr4m_fw658.webp" \
         "$WIKI_IMG_DIR/guanfang_cover.webp"
download "$CDN_IMG/R-C.jpg"                        "$WIKI_IMG_DIR/personal_cover.jpg"

echo ""
echo "✅ 全部下载完成。目录清单："
echo "  $LIVE2D_DIR/  -> $(ls -1 "$LIVE2D_DIR" | grep -v .gitkeep | wc -l) 个文件"
echo "  $JS_DIR/      -> $(ls -1 "$JS_DIR" | grep -v .gitkeep | wc -l) 个文件"
echo "  $GIF_DIR/     -> $(ls -1 "$GIF_DIR" | grep -v .gitkeep | wc -l) 个文件"
echo "  $WIKI_IMG_DIR/-> $(ls -1 "$WIKI_IMG_DIR" | grep -v .gitkeep | wc -l) 个文件"
echo ""
echo "重启服务后生效：systemctl restart forum-new  或  手动 kill 后重新启动 waitress-serve"
