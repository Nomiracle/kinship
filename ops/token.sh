#!/usr/bin/env bash
# Kinship Archive —— 页面口令管理
#
#   bash ops/token.sh show     打印当前口令（本地终端用）
#   bash ops/token.sh copy     复制到剪贴板（macOS）
#   bash ops/token.sh rotate   随机生成新口令并重启服务
#   bash ops/token.sh set      手动设一个自己好记的口令（交互输入，不进 shell 历史）
#   bash ops/token.sh where    只显示口令存在哪个文件
#
# ★ 口令只存在 deploy/.env（仓库之外、600 权限），永远不要提交或贴到聊天里。
#   它是局域网访问的唯一门槛：同网段的人拿到就能看全部数据。
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
deploy_dir="${ARCHIVE_DEPLOY_DIR:-$(cd "$root/../deploy" && pwd)}"
env_file="$deploy_dir/.env"

[ -f "$env_file" ] || { echo "缺少 $env_file" >&2; exit 1; }

current() {
  grep -E '^ARCHIVE_TOKEN=' "$env_file" | head -1 | cut -d= -f2-
}

write_token() {
  local new="$1"
  tmp=$(mktemp)
  chmod 600 "$tmp"
  awk -v t="$new" '
    /^ARCHIVE_TOKEN=/ { print "ARCHIVE_TOKEN=" t; found=1; next }
    { print }
    END { if (!found) print "ARCHIVE_TOKEN=" t }
  ' "$env_file" > "$tmp"
  mv "$tmp" "$env_file"
  chmod 600 "$env_file"
}

restart() {
  echo "· 重启服务让新口令生效"
  ( cd "$root" && bash ops/serve.sh stop >/dev/null 2>&1 || true; bash ops/serve.sh start )
}

case "${1:-show}" in
  show)
    current
    ;;
  copy)
    if command -v pbcopy >/dev/null 2>&1; then
      current | pbcopy
      echo "已复制到剪贴板（$(current | wc -c | tr -d ' ') 字符，未在此显示）"
    else
      echo "没有 pbcopy，请用 show 子命令" >&2
      exit 1
    fi
    ;;
  where)
    echo "$env_file"
    ;;
  rotate)
    new=$(LC_ALL=C tr -dc 'A-Za-z0-9' </dev/urandom | head -c 32)
    write_token "$new"
    echo "已生成新口令（32 字符，未在此显示）"
    restart
    ;;
  set)
    printf '输入新口令（不回显）: ' >&2
    read -rs new
    echo >&2
    [ -n "$new" ] || { echo "口令不能为空" >&2; exit 1; }
    write_token "$new"
    echo "已更新"
    restart
    ;;
  *)
    echo "用法：$0 {show|copy|rotate|set|where}" >&2
    exit 2
    ;;
esac
