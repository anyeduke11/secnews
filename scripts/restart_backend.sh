#!/usr/bin/env bash
# restart_backend.sh — dev即生产 标准停机/重启 SOP (DEV-0303 R5)。
#
# 单命令固化此前手工四步 (找 pid → TERM → 确认 → 重启), 全程计时:
#   1. 定位端口监听者所在进程组 (含 dsh/pi 等同组子进程)
#   2. TERM 整组 → 有界等端口释放 (默认 20s, 覆盖 uvicorn 15s 排空 + ε)
#   3. 超时未释放 → 逃逸 KILL 整组
#   4. exec python run.py 前台启动 (启动闸自带单实例收割, R4)
#
# 用法:
#   scripts/restart_backend.sh                # 停机(有界) → 启动
#   scripts/restart_backend.sh --stop-only    # 只停不起
#
# 环境变量:
#   HOTSPOT_PORT       目标端口 (默认 8000)
#   HOTSPOT_STOP_WAIT  TERM 后等端口释放上限秒 (默认 20)
set -u
cd "$(dirname "$0")/.."
PORT="${HOTSPOT_PORT:-8000}"
STOP_WAIT="${HOTSPOT_STOP_WAIT:-20}"
STOP_ONLY=0
[ "${1:-}" = "--stop-only" ] && STOP_ONLY=1

port_listener() { lsof -t -nP -iTCP:"$PORT" -sTCP:LISTEN 2>/dev/null | head -1; }

t0=$(date +%s)
PID="$(port_listener)"
if [ -n "$PID" ]; then
  PGID="$(ps -o pgid= -p "$PID" | tr -d ' ')"
  MY_PGID="$(ps -o pgid= -p $$ | tr -d ' ')"
  echo "[restart] TERM 进程组 -$PGID (listener pid $PID, port $PORT)"
  if [ "$PGID" = "$MY_PGID" ]; then
    # 同组 (本 shell 直接拉起的服务器): 只杀目标 pid, 防自杀
    kill -TERM "$PID" 2>/dev/null
  else
    kill -TERM -- "-$PGID" 2>/dev/null || kill -TERM "$PID" 2>/dev/null
  fi
  for ((i = 0; i < STOP_WAIT * 2; i++)); do
    [ -z "$(port_listener)" ] && break
    sleep 0.5
  done
  if [ -n "$(port_listener)" ]; then
    echo "[restart] ${STOP_WAIT}s 未释放 → 逃逸 KILL"
    if [ "$PGID" = "$MY_PGID" ]; then
      kill -KILL "$PID" 2>/dev/null
    else
      kill -KILL -- "-$PGID" 2>/dev/null || kill -KILL "$PID" 2>/dev/null
    fi
    sleep 1
  fi
  echo "[restart] 停机完成, 耗时 $(( $(date +%s) - t0 ))s"
else
  echo "[restart] 端口 $PORT 无监听者 (未在跑)"
fi

if [ "$STOP_ONLY" = "1" ]; then
  exit 0
fi

PY=python3
[ -x .venv/bin/python3 ] && PY=.venv/bin/python3
echo "[restart] 启动后端 ($PY run.py, 前台)…"
exec "$PY" run.py
