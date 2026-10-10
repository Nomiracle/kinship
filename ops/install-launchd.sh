#!/usr/bin/env bash
# 把 ops/launchd/*.plist.template 渲染成本机可用 plist（仓库内不出现绝对路径）
set -euo pipefail

# 仓库根 = 本脚本所在目录的上一级（不依赖 cwd，也不依赖 git 可用）
# ★ 教训：cron / 调度器执行时 cwd 不是仓库，`git rev-parse` 会直接失败（exit 128）
root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
app_dir="$root"
deploy_dir="${ARCHIVE_DEPLOY_DIR:-$(cd "$root/../deploy" && pwd)}"
port="${ARCHIVE_PORT:-8787}"
dest="$HOME/Library/LaunchAgents"

mkdir -p "$dest" "$deploy_dir/logs"

for tpl in "$root"/ops/launchd/*.plist.template; do
  name=$(basename "$tpl" .template)
  sed -e "s|__HOME__|$HOME|g" \
      -e "s|__APP_DIR__|$app_dir|g" \
      -e "s|__DEPLOY_DIR__|$deploy_dir|g" \
      -e "s|__PORT__|$port|g" \
      "$tpl" > "$dest/$name"
  echo "rendered $dest/$name"
done

echo
echo "下一步："
echo "  launchctl load -w $dest/com.kinship-archive.api.plist"
