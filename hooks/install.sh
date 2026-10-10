#!/usr/bin/env bash
# 安装 git 钩子：把 hooks/ 下的脚本软链到 .git/hooks/
set -euo pipefail
root=$(git rev-parse --show-toplevel)
mkdir -p "$root/.git/hooks"
for h in "$root"/hooks/*; do
  name=$(basename "$h")
  [ "$name" = "install.sh" ] && continue
  chmod +x "$h"
  ln -sf "../../hooks/$name" "$root/.git/hooks/$name"
  echo "linked .git/hooks/$name"
done
