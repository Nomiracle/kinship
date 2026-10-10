#!/usr/bin/env bash
# Kinship Archive — 初始化 MySQL 库与专用账号
#
# 特性：
#   · 通用脚本，零个人数据（库名/账号/口令全部来自 deploy/.env）
#   · 口令不经命令行传递（避免出现在 ps 与 shell 历史），走临时 defaults-file
#   · 字符集强制 utf8mb4 / utf8mb4_0900_ai_ci
#   · 建库后自检 ngram 中文全文检索，避免「配好了却搜不到」
#
# 用法：
#   ARCHIVE_ROOT_PWD=<root口令> bash ops/setup-db.sh      # root 有口令时
#   bash ops/setup-db.sh                                  # root 无口令（本机 fresh install）
set -euo pipefail

# 仓库根 = 本脚本所在目录的上一级（不依赖 cwd，也不依赖 git 可用）
# ★ 教训：cron / 调度器执行时 cwd 不是仓库，`git rev-parse` 会直接失败（exit 128）
root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
deploy_dir="${ARCHIVE_DEPLOY_DIR:-$(cd "$root/../deploy" && pwd)}"
env_file="$deploy_dir/.env"

[ -f "$env_file" ] || { echo "缺少 $env_file（从 .env.example 复制并填写）" >&2; exit 1; }
# shellcheck disable=SC1090
set -a; . "$env_file"; set +a
: "${ARCHIVE_DB_NAME:?ARCHIVE_DB_NAME 未设置}"
: "${ARCHIVE_DB_USER:?ARCHIVE_DB_USER 未设置}"
: "${ARCHIVE_DB_PASSWORD:?ARCHIVE_DB_PASSWORD 未设置}"

# --- 定位客户端（brew 的 mysql@8.4 是 keg-only，不进 PATH）---
MYSQL_BIN="${MYSQL_BIN:-$(command -v mysql || true)}"
if [ -z "$MYSQL_BIN" ]; then
  for c in /opt/homebrew/opt/mysql@8.4/bin/mysql /usr/local/opt/mysql@8.4/bin/mysql /opt/homebrew/bin/mysql; do
    if [ -x "$c" ]; then MYSQL_BIN="$c"; break; fi
  done
fi
[ -n "$MYSQL_BIN" ] || { echo "找不到 mysql 客户端，请设置 MYSQL_BIN" >&2; exit 1; }
echo "· 客户端：$MYSQL_BIN"

tmp=$(mktemp -d)
chmod 700 "$tmp"
trap 'rm -rf "$tmp"' EXIT

# root 连接配置：优先用 ARCHIVE_ROOT_PWD；失败或未设置则回退到「无口令」
# （Homebrew 全新安装的 root 没有口令，这条回退让首次初始化也能一把过）
root_cnf="$tmp/root.cnf"
umask 077
write_root_cnf() {
  {
    echo "[client]"
    echo "host=127.0.0.1"
    echo "port=${ARCHIVE_DB_PORT:-3306}"
    echo "user=root"
    echo "default-character-set=utf8mb4"
    # ★ 必须用 if，不能写 `[ -n "$1" ] && echo ...`：
    #   set -e 下该 AND 列表在条件为假时返回 1，函数返回 1，脚本会静默中止
    if [ -n "${1:-}" ]; then
      echo "password=${1}"
    fi
  } > "$root_cnf"
}
write_root_cnf "${ARCHIVE_ROOT_PWD:-}"
if ! "$MYSQL_BIN" --defaults-extra-file="$root_cnf" -e 'SELECT 1' >/dev/null 2>&1; then
  if [ -n "${ARCHIVE_ROOT_PWD:-}" ]; then
    echo "· 带口令连接 root 失败，尝试无口令（fresh install 场景）"
  fi
  write_root_cnf ""
  "$MYSQL_BIN" --defaults-extra-file="$root_cnf" -e 'SELECT 1' >/dev/null 2>&1 \
    || { echo "无法以 root 连接 MySQL，请检查服务是否启动/口令是否正确" >&2; exit 1; }
fi

# 应用账号连接配置
app_cnf="$tmp/app.cnf"
{
  echo "[client]"
  echo "host=127.0.0.1"
  echo "port=${ARCHIVE_DB_PORT:-3306}"
  echo "user=${ARCHIVE_DB_USER}"
  echo "password=${ARCHIVE_DB_PASSWORD}"
  echo "default-character-set=utf8mb4"
} > "$app_cnf"

echo "· 建库 ${ARCHIVE_DB_NAME}（utf8mb4 / utf8mb4_0900_ai_ci）"
"$MYSQL_BIN" --defaults-extra-file="$root_cnf" <<SQL
CREATE DATABASE IF NOT EXISTS \`${ARCHIVE_DB_NAME}\`
  CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci;
CREATE USER IF NOT EXISTS '${ARCHIVE_DB_USER}'@'127.0.0.1' IDENTIFIED BY '${ARCHIVE_DB_PASSWORD}';
CREATE USER IF NOT EXISTS '${ARCHIVE_DB_USER}'@'localhost' IDENTIFIED BY '${ARCHIVE_DB_PASSWORD}';
ALTER USER '${ARCHIVE_DB_USER}'@'127.0.0.1' IDENTIFIED BY '${ARCHIVE_DB_PASSWORD}';
GRANT ALL PRIVILEGES ON \`${ARCHIVE_DB_NAME}\`.* TO '${ARCHIVE_DB_USER}'@'127.0.0.1';
GRANT ALL PRIVILEGES ON \`${ARCHIVE_DB_NAME}\`.* TO '${ARCHIVE_DB_USER}'@'localhost';
FLUSH PRIVILEGES;
SQL

echo "· 自检：字符集"
"$MYSQL_BIN" --defaults-extra-file="$app_cnf" -N -B -e \
  "SELECT DEFAULT_CHARACTER_SET_NAME, DEFAULT_COLLATION_NAME
     FROM information_schema.SCHEMATA WHERE SCHEMA_NAME='${ARCHIVE_DB_NAME}';"

echo "· 自检：ngram 中文全文检索"
# 注意：FULLTEXT 索引不能建在 TEMPORARY InnoDB 表上（ERROR 1796），必须用真实表
"$MYSQL_BIN" --defaults-extra-file="$app_cnf" -N -B "$ARCHIVE_DB_NAME" <<'SQL'
DROP TABLE IF EXISTS _ngram_probe;
CREATE TABLE _ngram_probe (
  id INT PRIMARY KEY AUTO_INCREMENT, body TEXT,
  FULLTEXT KEY ft_body (body) WITH PARSER ngram
) ENGINE=InnoDB;
INSERT INTO _ngram_probe (body) VALUES ('棕色马甲配黑色裙子'), ('白色运动外套');
SELECT 'ngram 2字命中(预期1):', COUNT(*) FROM _ngram_probe WHERE MATCH(body) AGAINST('棕色' IN BOOLEAN MODE);
SELECT 'ngram 1字命中(预期0):', COUNT(*) FROM _ngram_probe WHERE MATCH(body) AGAINST('棕' IN BOOLEAN MODE);
DROP TABLE _ngram_probe;
SQL

echo
echo "✓ 完成。库=${ARCHIVE_DB_NAME} 账号=${ARCHIVE_DB_USER}（口令未在此输出）"
echo "  注：ngram_token_size 默认 2 —— 单字查询必然 0 命中，后端需对 <=2 字的查询回退 LIKE。"
