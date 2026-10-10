#!/usr/bin/env bash
# Kinship Archive — 备份（数据库 + 媒体）
#
#   bash ops/backup.sh              # 执行一次
#   RETAIN_DAYS=30 bash ops/backup.sh
#
# 设计：
#   · 通用、零个人数据；路径与口令来自 deploy/.env
#   · 数据库用 mysqldump --single-transaction（不锁表）
#   · 媒体用 rsync --link-dest 硬链接快照，省空间且可回溯
#   · 备份产物全部落在 deploy/backups/（在 git 仓库之外，永不提交）
set -euo pipefail

# 仓库根 = 本脚本所在目录的上一级（不依赖 cwd，也不依赖 git 可用）
# ★ 教训：cron / 调度器执行时 cwd 不是仓库，`git rev-parse` 会直接失败（exit 128）
root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
deploy_dir="${ARCHIVE_DEPLOY_DIR:-$(cd "$root/../deploy" && pwd)}"
env_file="$deploy_dir/.env"
[ -f "$env_file" ] || { echo "缺少 $env_file" >&2; exit 1; }
# shellcheck disable=SC1090
set -a; . "$env_file"; set +a

RETAIN_DAYS="${RETAIN_DAYS:-30}"
stamp=$(date +%Y%m%d-%H%M%S)
backup_root="$deploy_dir/backups"
db_dir="$backup_root/db"
media_dir="$backup_root/media"
log="$deploy_dir/logs/backup.log"
mkdir -p "$db_dir" "$media_dir" "$deploy_dir/logs"

logf() { printf '%s %s\n' "$(date '+%F %T')" "$*" | tee -a "$log"; }

MYSQLDUMP_BIN="${MYSQLDUMP_BIN:-$(command -v mysqldump || true)}"
if [ -z "$MYSQLDUMP_BIN" ]; then
  for c in /opt/homebrew/opt/mysql@8.4/bin/mysqldump /usr/local/opt/mysql@8.4/bin/mysqldump; do
    if [ -x "$c" ]; then MYSQLDUMP_BIN="$c"; break; fi
  done
fi
[ -n "$MYSQLDUMP_BIN" ] || { logf "找不到 mysqldump，跳过数据库备份"; exit 1; }

tmp=$(mktemp -d); chmod 700 "$tmp"; trap 'rm -rf "$tmp"' EXIT
cnf="$tmp/app.cnf"; umask 077
{
  echo "[client]"
  echo "host=${ARCHIVE_DB_HOST:-127.0.0.1}"
  echo "port=${ARCHIVE_DB_PORT:-3306}"
  echo "user=${ARCHIVE_DB_USER}"
  echo "password=${ARCHIVE_DB_PASSWORD}"
} > "$cnf"

out="$db_dir/${ARCHIVE_DB_NAME}-${stamp}.sql.gz"
# --no-tablespaces：应用账号无 PROCESS 权限，缺了它 mysqldump 会报
#   "Access denied; you need ... PROCESS privilege(s) ... tablespaces"
if "$MYSQLDUMP_BIN" --defaults-extra-file="$cnf" \
     --single-transaction --quick --no-tablespaces --routines --events \
     --default-character-set=utf8mb4 "${ARCHIVE_DB_NAME}" | gzip -9 > "$out"; then
  logf "db   → $(basename "$out")  $(du -h "$out" | cut -f1)"
else
  logf "db   备份失败"; exit 1
fi

# 媒体：硬链接快照（媒体文件不变，省磁盘）
if [ -d "$deploy_dir/media" ]; then
  link_ref=$(ls -1dt "$media_dir"/[0-9]* 2>/dev/null | head -1 || true)
  if [ -n "$link_ref" ]; then
    rsync -a --delete --link-dest="$link_ref" "$deploy_dir/media/" "$media_dir/$stamp/"
  else
    rsync -a "$deploy_dir/media/" "$media_dir/$stamp/"
  fi
  logf "media→ $stamp/ ($(find "$deploy_dir/media" -type f | wc -l | tr -d ' ') 个文件)"
fi

# 过期清理
find "$db_dir" -name '*.sql.gz' -type f -mtime +"$RETAIN_DAYS" -delete
find "$media_dir" -maxdepth 1 -mindepth 1 -type d -mtime +"$RETAIN_DAYS" -exec rm -rf {} +
logf "清理：保留 ${RETAIN_DAYS} 天"

logf "✓ 备份完成 → $backup_root"
