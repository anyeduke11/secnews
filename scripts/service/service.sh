#!/usr/bin/env bash
# =============================================================================
# hotspot 服务管理脚本 — 前后端启停/重启/状态
# =============================================================================
# 用法:
#   ./scripts/service/service.sh start   [--all|--backend|--frontend]
#   ./scripts/service/service.sh stop    [--all|--backend|--frontend]
#   ./scripts/service/service.sh restart [--all|--backend|--frontend]
#   ./scripts/service/service.sh status  [--all|--backend|--frontend]
#   ./scripts/service/service.sh logs    [backend|frontend]
#   ./scripts/service/service.sh help
#
# 默认粒度: --all (同时管后端+前端)
# 端口: 后端 8000,前端 8898
# PID 文件: scripts/logs/{backend,frontend}.pid
# 日志: scripts/logs/{backend,frontend}.out.log
#
# 设计原则:
# - macOS 兼容(用 lsof 不用 netstat,BSD sed 不要 -i.bak 后缀)
# - PID 文件 + 端口探测双重定位,避免误杀
# - stop: 先 SIGTERM 5s 优雅退出,后 SIGKILL 兜底
# - start: 启动后探测 /api/health 验证就绪(最多 30s)
# - npm 进程树: 杀 node(监听端口) + 父 npm
# =============================================================================

set -u

# ----- 路径与端口 -----
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
LOG_DIR="$PROJECT_ROOT/scripts/logs"
mkdir -p "$LOG_DIR"

BACKEND_PORT=8000
FRONTEND_PORT=8898
BACKEND_PIDFILE="$LOG_DIR/backend.pid"
FRONTEND_PIDFILE="$LOG_DIR/frontend.pid"
BACKEND_LOG="$LOG_DIR/backend.out.log"
FRONTEND_LOG="$LOG_DIR/frontend.out.log"
BACKEND_HEALTH_URL="http://127.0.0.1:$BACKEND_PORT/api/health"
FRONTEND_URL="http://127.0.0.1:$FRONTEND_PORT/"

BACKEND_CMD=(".venv/bin/python" "run.py")
FRONTEND_DIR="$PROJECT_ROOT/frontend"
FRONTEND_CMD=(npm run dev)

# ----- 颜色 -----
if [ -t 1 ]; then
    RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[0;33m'
    CYAN='\033[0;36m'; BOLD='\033[1m'; RESET='\033[0m'
else
    RED=''; GREEN=''; YELLOW=''; CYAN=''; BOLD=''; RESET=''
fi

log_info()  { printf "${CYAN}[service]${RESET} %s\n" "$*"; }
log_ok()    { printf "${GREEN}[service]${RESET} %s\n" "$*"; }
log_warn()  { printf "${YELLOW}[service]${RESET} %s\n" "$*"; }
log_err()   { printf "${RED}[service]${RESET} %s\n" "$*" >&2; }
log_title() { printf "${BOLD}${CYAN}==== %s ====${RESET}\n" "$*"; }

# ----- 工具 -----
# 端口监听进程的 PID（lsof -ti :PORT -sTCP:LISTEN）
port_pids() {
    lsof -ti :"$1" -sTCP:LISTEN 2>/dev/null
}

# 进程是否存活
is_alive() {
    [ -n "$1" ] && kill -0 "$1" 2>/dev/null
}

# 读 PID 文件
read_pid() {
    local f="$1"
    [ -f "$f" ] || return 1
    local p
    p=$(cat "$f" 2>/dev/null)
    [ -n "$p" ] || return 1
    echo "$p"
}

# 清理过期 PID 文件（PID 文件存在但进程不在）
cleanup_stale_pidfile() {
    local f="$1"
    local p
    p=$(read_pid "$f" 2>/dev/null) || { rm -f "$f"; return 1; }
    if ! is_alive "$p"; then
        rm -f "$f"
        return 1
    fi
    return 0
}

# 等待 URL 200（最多 N 秒）
wait_http_200() {
    local url="$1" timeout="${2:-30}"
    local deadline=$((SECONDS + timeout))
    while [ $SECONDS -lt $deadline ]; do
        local code
        code=$(curl -s -o /dev/null -w "%{http_code}" --max-time 3 "$url" 2>/dev/null || echo "000")
        if [ "$code" = "200" ]; then
            return 0
        fi
        sleep 1
    done
    return 1
}

# 杀进程树（先 SIGTERM，后 SIGKILL）
# 输入: $1=PID, $2=超时秒数（默认 8）
kill_tree() {
    local pid="$1" timeout="${2:-8}"
    if ! is_alive "$pid"; then
        return 0
    fi
    # 杀子进程（npm 启动的 node 也要杀）
    local children
    children=$(pgrep -P "$pid" 2>/dev/null || true)
    kill -TERM "$pid" 2>/dev/null || true
    for c in $children; do
        kill -TERM "$c" 2>/dev/null || true
    done
    # 等
    local deadline=$((SECONDS + timeout))
    while [ $SECONDS -lt $deadline ]; do
        if ! is_alive "$pid"; then
            return 0
        fi
        sleep 1
    done
    # 兜底 SIGKILL
    log_warn "PID $pid 未在 ${timeout}s 内退出, SIGKILL 兜底"
    kill -KILL "$pid" 2>/dev/null || true
    for c in $children; do
        kill -KILL "$c" 2>/dev/null || true
    done
    sleep 1
    return 0
}

# =============================================================================
# 后端
# =============================================================================
start_backend() {
    log_title "启动后端 (port=$BACKEND_PORT)"

    # 端口占用检查
    local occupied
    occupied=$(port_pids "$BACKEND_PORT")
    if [ -n "$occupied" ]; then
        log_warn "端口 $BACKEND_PORT 已被 PID=$occupied 占用,跳过启动"
        return 0
    fi

    # 过期 PID 文件清理
    if ! cleanup_stale_pidfile "$BACKEND_PIDFILE"; then
        : # 已清理
    fi
    if [ -f "$BACKEND_PIDFILE" ]; then
        local existing
        existing=$(cat "$BACKEND_PIDFILE")
        if is_alive "$existing"; then
            log_warn "后端 PID $existing 仍在运行,跳过启动"
            return 0
        fi
        rm -f "$BACKEND_PIDFILE"
    fi

    cd "$PROJECT_ROOT" || { log_err "cd $PROJECT_ROOT 失败"; return 1; }

    log_info "cwd: $PROJECT_ROOT"
    log_info "cmd: ${BACKEND_CMD[*]}"
    log_info "log: $BACKEND_LOG"

    # 后台启动
    nohup "${BACKEND_CMD[@]}" > "$BACKEND_LOG" 2>&1 &
    local pid=$!
    echo "$pid" > "$BACKEND_PIDFILE"
    log_ok "已启动后端 pid=$pid"

    # 验证 /api/health
    log_info "等待 /api/health 就绪..."
    if wait_http_200 "$BACKEND_HEALTH_URL" 30; then
        log_ok "/api/health 200 [OK]"
    else
        log_warn "/api/health 30s 内未就绪,查看 $BACKEND_LOG"
        return 1
    fi
}

stop_backend() {
    log_title "停止后端 (port=$BACKEND_PORT)"

    # 优先 PID 文件
    local pid=""
    if [ -f "$BACKEND_PIDFILE" ]; then
        pid=$(cat "$BACKEND_PIDFILE" 2>/dev/null || true)
        if ! is_alive "$pid"; then pid=""; fi
    fi
    # PID 文件拿不到,按端口找
    if [ -z "$pid" ]; then
        pid=$(port_pids "$BACKEND_PORT" | head -1)
    fi

    if [ -z "$pid" ]; then
        log_warn "后端未运行"
        rm -f "$BACKEND_PIDFILE"
        return 0
    fi

    log_info "停止后端 pid=$pid (SIGTERM, 8s 超时)"
    kill_tree "$pid" 8
    rm -f "$BACKEND_PIDFILE"

    # 验证端口释放
    if port_pids "$BACKEND_PORT" >/dev/null; then
        log_warn "端口 $BACKEND_PORT 仍被占用"
    else
        log_ok "后端已停止,端口 $BACKEND_PORT 已释放"
    fi
}

status_backend() {
    local pid=""
    if [ -f "$BACKEND_PIDFILE" ]; then
        pid=$(cat "$BACKEND_PIDFILE" 2>/dev/null || true)
    fi
    if [ -z "$pid" ] || ! is_alive "$pid"; then
        # 端口探测兜底
        pid=$(port_pids "$BACKEND_PORT" | head -1)
    fi
    if [ -z "$pid" ] || ! is_alive "$pid"; then
        log_warn "后端: 未运行 (port=$BACKEND_PORT)"
        return 1
    fi
    local code
    code=$(curl -s -o /dev/null -w "%{http_code}" --max-time 3 "$BACKEND_HEALTH_URL" 2>/dev/null || echo "000")
    if [ "$code" = "200" ]; then
        local ver up
        ver=$(curl -s --max-time 3 "$BACKEND_HEALTH_URL" 2>/dev/null | python3 -c "import json,sys;d=json.load(sys.stdin);print(d.get('version','?'))" 2>/dev/null || echo "?")
        up=$(curl -s --max-time 3 "$BACKEND_HEALTH_URL" 2>/dev/null | python3 -c "import json,sys;d=json.load(sys.stdin);print(int(d.get('uptime_s',0)))" 2>/dev/null || echo "?")
        log_ok "后端: 运行中 pid=$pid port=$BACKEND_PORT version=$ver uptime=${up}s"
    else
        log_warn "后端: 进程存活但 /api/health 返回 HTTP $code"
    fi
}

# =============================================================================
# 前端
# =============================================================================
start_frontend() {
    log_title "启动前端 (port=$FRONTEND_PORT)"

    local occupied
    occupied=$(port_pids "$FRONTEND_PORT")
    if [ -n "$occupied" ]; then
        log_warn "端口 $FRONTEND_PORT 已被 PID=$occupied 占用,跳过启动"
        return 0
    fi

    if [ -f "$FRONTEND_PIDFILE" ]; then
        local existing
        existing=$(cat "$FRONTEND_PIDFILE")
        if is_alive "$existing"; then
            log_warn "前端 PID $existing 仍在运行,跳过启动"
            return 0
        fi
        rm -f "$FRONTEND_PIDFILE"
    fi

    if [ ! -d "$FRONTEND_DIR" ]; then
        log_err "前端目录不存在: $FRONTEND_DIR"
        return 1
    fi

    cd "$FRONTEND_DIR" || { log_err "cd $FRONTEND_DIR 失败"; return 1; }

    log_info "cwd: $FRONTEND_DIR"
    log_info "cmd: ${FRONTEND_CMD[*]}"
    log_info "log: $FRONTEND_LOG"

    nohup "${FRONTEND_CMD[@]}" > "$FRONTEND_LOG" 2>&1 &
    local pid=$!
    echo "$pid" > "$FRONTEND_PIDFILE"
    log_ok "已启动前端 pid=$pid"

    # Vite 启动较快,等 3s 后探测
    log_info "等待前端就绪..."
    if wait_http_200 "$FRONTEND_URL" 30; then
        log_ok "$FRONTEND_URL 200 [OK]"
    else
        log_warn "前端 30s 内未就绪,查看 $FRONTEND_LOG"
        return 1
    fi
}

stop_frontend() {
    log_title "停止前端 (port=$FRONTEND_PORT)"

    local pid=""
    if [ -f "$FRONTEND_PIDFILE" ]; then
        pid=$(cat "$FRONTEND_PIDFILE" 2>/dev/null || true)
        if ! is_alive "$pid"; then pid=""; fi
    fi
    if [ -z "$pid" ]; then
        pid=$(port_pids "$FRONTEND_PORT" | head -1)
    fi

    if [ -z "$pid" ]; then
        log_warn "前端未运行"
        rm -f "$FRONTEND_PIDFILE"
        return 0
    fi

    log_info "停止前端 pid=$pid (SIGTERM, 8s 超时,杀进程树)"
    kill_tree "$pid" 8
    rm -f "$FRONTEND_PIDFILE"

    if port_pids "$FRONTEND_PORT" >/dev/null; then
        log_warn "端口 $FRONTEND_PORT 仍被占用,尝试直接 kill 监听进程"
        # 兜底
        local remaining
        remaining=$(port_pids "$FRONTEND_PORT")
        for r in $remaining; do
            kill -KILL "$r" 2>/dev/null || true
        done
    else
        log_ok "前端已停止,端口 $FRONTEND_PORT 已释放"
    fi
}

status_frontend() {
    local pid=""
    if [ -f "$FRONTEND_PIDFILE" ]; then
        pid=$(cat "$FRONTEND_PIDFILE" 2>/dev/null || true)
    fi
    if [ -z "$pid" ] || ! is_alive "$pid"; then
        pid=$(port_pids "$FRONTEND_PORT" | head -1)
    fi
    if [ -z "$pid" ] || ! is_alive "$pid"; then
        log_warn "前端: 未运行 (port=$FRONTEND_PORT)"
        return 1
    fi
    local code
    code=$(curl -s -o /dev/null -w "%{http_code}" --max-time 3 "$FRONTEND_URL" 2>/dev/null || echo "000")
    if [ "$code" = "200" ]; then
        log_ok "前端: 运行中 pid=$pid port=$FRONTEND_PORT"
    else
        log_warn "前端: 进程存活但 $FRONTEND_URL 返回 HTTP $code"
    fi
}

# =============================================================================
# 复合动作
# =============================================================================
do_start() {
    local target="${1:-all}"
    case "$target" in
        all)      start_backend; start_frontend ;;
        backend)  start_backend ;;
        frontend) start_frontend ;;
        *) log_err "未知粒度: $target"; return 2 ;;
    esac
}

do_stop() {
    local target="${1:-all}"
    case "$target" in
        all)      stop_frontend; stop_backend ;;
        backend)  stop_backend ;;
        frontend) stop_frontend ;;
        *) log_err "未知粒度: $target"; return 2 ;;
    esac
}

do_restart() {
    local target="${1:-all}"
    case "$target" in
        all)      do_stop all; sleep 1; do_start all ;;
        backend)  stop_backend; sleep 1; start_backend ;;
        frontend) stop_frontend; sleep 1; start_frontend ;;
        *) log_err "未知粒度: $target"; return 2 ;;
    esac
}

do_status() {
    local target="${1:-all}"
    case "$target" in
        all)
            status_backend; status_frontend
            ;;
        backend)  status_backend ;;
        frontend) status_frontend ;;
        *) log_err "未知粒度: $target"; return 2 ;;
    esac
}

do_logs() {
    local target="${1:-backend}"
    case "$target" in
        backend)
            log_info "tail -f $BACKEND_LOG (Ctrl+C 退出)"
            tail -f "$BACKEND_LOG"
            ;;
        frontend)
            log_info "tail -f $FRONTEND_LOG (Ctrl+C 退出)"
            tail -f "$FRONTEND_LOG"
            ;;
        *) log_err "未知 logs 目标: $target (backend|frontend)"; return 2 ;;
    esac
}

do_help() {
    sed -n '3,30p' "$0" | sed 's/^# \{0,1\}//'
}

# =============================================================================
# 入口
# =============================================================================
main() {
    local action="${1:-help}"
    shift || true
    local target="all"
    while [ $# -gt 0 ]; do
        case "$1" in
            --all)      target="all" ;;
            --backend)  target="backend" ;;
            --frontend) target="frontend" ;;
            -h|--help|help) action="help" ;;
            *) log_err "未知参数: $1"; action="help" ;;
        esac
        shift || true
    done

    case "$action" in
        start)   do_start "$target" ;;
        stop)    do_stop "$target" ;;
        restart) do_restart "$target" ;;
        status)  do_status "$target" ;;
        logs)    do_logs "$target" ;;
        help|-h|--help) do_help ;;
        *) log_err "未知动作: $action (start|stop|restart|status|logs|help)"; do_help; return 2 ;;
    esac
}

main "$@"
