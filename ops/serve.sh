#!/usr/bin/env bash
# Kinship Archive —— 服务启停 / 守护
#
#   bash ops/serve.sh start    启动（后台，写 pidfile）
#   bash ops/serve.sh stop     停止
#   bash ops/serve.sh status   探活（直接打 /api/health，比 pidfile 可信）
#   bash ops/serve.sh ensure   没跑就启动（给定时任务/守护用）
#
# ★ 为什么不用 launchd：macOS 的 TCC 保护 ~/Desktop 等目录，
#   launchd 拉起的进程读不到本方案放在桌面目录下的代码与 venv
#   （实测报 "Operation not permitted"，Python 会卡在解释器启动阶段）。
#   本脚本必须从已有桌面访问权限的上下文执行（终端 / 代理进程）。
#   若确实要用 launchd，需要给运行它的解释器授予「完全磁盘访问权限」。
set -euo pipefail

# 仓库根 = 本脚本所在目录的上一级（不依赖 cwd，也不依赖 git 可用）
# ★ 教训：cron / 调度器执行时 cwd 不是仓库，`git rev-parse` 会直接失败（exit 128）
root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
deploy_dir="${ARCHIVE_DEPLOY_DIR:-$(cd "$root/../deploy" && pwd)}"

if [ -f "$deploy_dir/.env" ]; then
  set -a
  # shellcheck disable=SC1090
  . "$deploy_dir/.env"
  set +a
fi

host="${ARCHIVE_HOST:-0.0.0.0}"
port="${ARCHIVE_PORT:-8787}"
pidfile="$deploy_dir/kinship-api.pid"
log="$deploy_dir/logs/api.out.log"
errlog="$deploy_dir/logs/api.error.log"
python="$root/.venv/bin/python"

mkdir -p "$deploy_dir/logs"

alive() {
  curl -s --max-time 3 -o /dev/null "http://127.0.0.1:${port}/api/health"
}

do_status() {
  if alive; then
    echo "running (pid $(cat "$pidfile" 2>/dev/null || echo '?'), port $port)"
    return 0
  fi
  echo "down"
  return 1
}

do_start() {
  if alive; then
    echo "already running on $port"
    return 0
  fi
  [ -x "$python" ] || { echo "缺少 venv：$python" >&2; exit 1; }
  cd "$root"
  nohup "$python" -m uvicorn backend.main:app \
    --host "$host" --port "$port" >>"$log" 2>"$errlog" &
  echo $! > "$pidfile"
  for _ in $(seq 1 30); do
    if alive; then echo "started (pid $(cat "$pidfile"), $host:$port)"; return 0; fi
    sleep 1
  done
  echo "启动失败，看 $errlog" >&2
  tail -20 "$errlog" >&2 || true
  return 1
}

do_stop() {
  if [ -f "$pidfile" ]; then
    pid=$(cat "$pidfile")
    kill "$pid" 2>/dev/null || true
    sleep 1
    kill -9 "$pid" 2>/dev/null || true
    rm -f "$pidfile"
    echo "stopped (pid $pid)"
  else
    echo "没有 pidfile，尝试按端口清理"
    pkill -f "uvicorn backend.main:app" 2>/dev/null || true
  fi
}

case "${1:-ensure}" in
  start) do_start ;;
  stop) do_stop ;;
  status) do_status ;;
  ensure) do_status >/dev/null 2>&1 || do_start ;;
  *) echo "用法：$0 {start|stop|status|ensure}" >&2; exit 2 ;;
esac
