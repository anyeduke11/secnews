#!/usr/bin/env bash
# T02-C 开发环境配置模板 — 独立数据根 + 关闭自动出站 + 端口错开 + dry-run 默认
#
# 用法 (从仓库根):
#   bash scripts/dev_environment.sh plan                  # 仅打印计划
#   bash scripts/dev_environment.sh init                  # 创建开发数据根 (dry-run 默认)
#   bash scripts/dev_environment.sh init --execute        # 真创建
#   bash scripts/dev_environment.sh start-backend         # 启动开发后端 (8000 端口, dev/prod 共用)
#   bash scripts/dev_environment.sh start-frontend        # 启动开发前端 (8898 端口)
#   bash scripts/dev_environment.sh status                # 查端口 / 进程 / 路径
#   bash scripts/dev_environment.sh stop                  # 停掉开发服务
#
# 设计原则 (EXECUTION_GUIDE §2.1, T02 段):
#   - 数据根独立: dev_data/ 在仓库内但 gitignored, 不与生产 backend/data 混淆
#   - 端口统一: 后端 8000 (dev/prod 共用, --strictPort), 前端 8898 (dev/prod 统一)
#     ⇒ 任一时刻只能跑一份后端 (dev 或 prod), 切换前需 stop 另一份
#     ⇒ 数据根仍隔离 (dev 走 dev_data/, prod 走仓库根 backend/data)
#   - 自动出站默认关: catchup_on_startup=0, collect_interval 不调
#   - 不改生产 db_path / wiki_root, 不调 BACKUP_RETENTION 链
#   - 远程同步 (WebDAV/git bundle) 默认不动, 等用户裁决
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DEV_ROOT="${REPO_ROOT}/dev_data"
DEV_DB_DIR="${DEV_ROOT}/db"
DEV_WIKI_DIR="${DEV_ROOT}/llm-wiki-2.0"
DEV_LOG_DIR="${DEV_ROOT}/logs"
DEV_BACKUP_DIR="${DEV_ROOT}/backups"
DEV_PORT_BACKEND="${DEV_PORT_BACKEND:-8000}"
DEV_PORT_FRONTEND="${DEV_PORT_FRONTEND:-8898}"

DRY_RUN=1
for arg in "$@"; do
    case "$arg" in
        --execute) DRY_RUN=0 ;;
    esac
done

log() { echo "[dev-env] $*"; }

action_init() {
    log "=== init dev environment ==="
    log "REPO_ROOT      = ${REPO_ROOT}"
    log "DEV_ROOT       = ${DEV_ROOT}"
    log "DEV_DB_DIR     = ${DEV_DB_DIR}"
    log "DEV_WIKI_DIR   = ${DEV_WIKI_DIR}"
    log "DEV_LOG_DIR    = ${DEV_LOG_DIR}"
    log "DEV_BACKUP_DIR = ${DEV_BACKUP_DIR}"
    log "BACKEND port   = ${DEV_PORT_BACKEND} (dev/prod 共用, --strictPort)"
    log "FRONTEND port  = ${DEV_PORT_FRONTEND} (dev/prod 统一, --strictPort)"
    log "mode           = $([[ $DRY_RUN -eq 1 ]] && echo DRY-RUN || echo EXECUTE)"

    if [[ $DRY_RUN -eq 1 ]]; then
        log "(dry-run: 跳过 mkdir / 模板生成)"
        return 0
    fi

    mkdir -p "${DEV_DB_DIR}" "${DEV_WIKI_DIR}" "${DEV_LOG_DIR}" "${DEV_BACKUP_DIR}"

    # .gitignore 增量: dev_data/ 不入仓
    local gi="${REPO_ROOT}/.gitignore"
    if [[ -f "$gi" ]] && ! grep -q "^dev_data/" "$gi" 2>/dev/null; then
        log "appending dev_data/ to .gitignore"
        printf "\n# T02-C dev environment (independent data root)\ndev_data/\n" >> "$gi"
    fi

    # 写一个 dev.env 模板, 供 source 复用
    cat > "${DEV_ROOT}/dev.env" <<EOF
# T02-C 开发环境变量 (source 此文件后再启后端/前端)
# 用法: source dev_data/dev.env && python run.py
export HOTSPOT_DB_PATH="${DEV_DB_DIR}/hotspot.db"
export HOTSPOT_WARM_DB_PATH="${DEV_DB_DIR}/hotspot-warm.db"
export HOTSPOT_COLD_DB_PATH="${DEV_DB_DIR}/hotspot-cold.db"
export HOTSPOT_DATA_DIR="${DEV_ROOT}/data"
export HOTSPOT_LOG_DIR="${DEV_LOG_DIR}"
export HOTSPOT_BACKUP_DIR="${DEV_BACKUP_DIR}"
export HOTSPOT_WIKI_ROOT="${DEV_WIKI_DIR}"
export HOTSPOT_PORT="${DEV_PORT_BACKEND}"
export HOTSPOT_HOST="127.0.0.1"

# 关闭自动出站 / 后台采集 / 启动追抓
export HOTSPOT_CATCHUP_ON_STARTUP=0
export HOTSPOT_PROXY_MODE=off
export HOTSPOT_REMOTE_BACKUP=    # 留空, 不推 WebDAV
export HOTSPOT_LLM_WIKI_V2=true
EOF
    log "wrote ${DEV_ROOT}/dev.env (source 后再启服务)"

    # 复制 wiki 模板 (空目录 + .gitkeep)
    [[ -f "${DEV_WIKI_DIR}/.gitkeep" ]] || touch "${DEV_WIKI_DIR}/.gitkeep"
    log "dev data roots ready. source ${DEV_ROOT}/dev.env to activate."
}

action_start_backend() {
    if [[ ! -f "${DEV_ROOT}/dev.env" ]]; then
        log "ERROR: dev.env not found, run 'init --execute' first"
        return 1
    fi
    # 端口占用检查
    if lsof -nP -iTCP:"${DEV_PORT_BACKEND}" -sTCP:LISTEN 2>/dev/null | grep -q LISTEN; then
        log "ERROR: port ${DEV_PORT_BACKEND} already in use"
        lsof -nP -iTCP:"${DEV_PORT_BACKEND}" -sTCP:LISTEN || true
        return 1
    fi
    log "starting backend on 127.0.0.1:${DEV_PORT_BACKEND} (env: dev.env)"
    cd "${REPO_ROOT}"
    # shellcheck disable=SC1091
    set -a; source "${DEV_ROOT}/dev.env"; set +a
    exec .venv/bin/python -m uvicorn backend.main:app \
        --host 127.0.0.1 --port "${DEV_PORT_BACKEND}" --workers 1 \
        --log-level info
}

action_start_frontend() {
    log "starting frontend on :${DEV_PORT_FRONTEND} (proxies 127.0.0.1:${DEV_PORT_BACKEND})"
    cd "${REPO_ROOT}/frontend"
    # v0.8.5 D2 修复: vite.config.ts 读的是 HOTSPOT_BACKEND_PORT (原误设 HOTSPOT_PORT,
    # 代理回落 8000 打到生产后端)。
    # v0.8.5 端口统一: dev/prod 前后端都固定 (后端 8000, 前端 8898, --strictPort)。
    # ⇒ 后端共用 8000 = 任一时刻只能跑一份, dev 切 prod 前必须 stop
    HOTSPOT_BACKEND_PORT="${DEV_PORT_BACKEND}" npm exec -- vite --port "${DEV_PORT_FRONTEND}" --strictPort --host 127.0.0.1
}

action_status() {
    log "=== dev environment status ==="
    log "REPO_ROOT: ${REPO_ROOT}"
    log "DEV_ROOT exists: $([[ -d ${DEV_ROOT} ]] && echo yes || echo no)"
    log "backend port ${DEV_PORT_BACKEND} LISTEN:"
    lsof -nP -iTCP:"${DEV_PORT_BACKEND}" -sTCP:LISTEN 2>/dev/null || echo "  (free)"
    log "frontend port ${DEV_PORT_FRONTEND} LISTEN:"
    lsof -nP -iTCP:"${DEV_PORT_FRONTEND}" -sTCP:LISTEN 2>/dev/null || echo "  (free)"
    log "backend 8000 LISTEN (dev/prod 共用, --strictPort):"
    lsof -nP -iTCP:8000 -sTCP:LISTEN 2>/dev/null || echo "  (free)"
    log "production frontend 8898 (与 dev 同端口):"
    lsof -nP -iTCP:8898 -sTCP:LISTEN 2>/dev/null || echo "  (free)"
}

action_stop() {
    log "stopping dev services (ports ${DEV_PORT_BACKEND}/${DEV_PORT_FRONTEND})"
    for port in "${DEV_PORT_BACKEND}" "${DEV_PORT_FRONTEND}"; do
        pids=$(lsof -nP -iTCP:"${port}" -sTCP:LISTEN -t 2>/dev/null || true)
        if [[ -n "${pids}" ]]; then
            log "kill port ${port} pids: ${pids}"
            kill ${pids} 2>/dev/null || true
        fi
    done
    log "done."
}

case "${1:-plan}" in
    plan)
        log "=== dev environment plan ==="
        action_init
        ;;
    init)
        action_init
        ;;
    start-backend)
        action_start_backend
        ;;
    start-frontend)
        action_start_frontend
        ;;
    status)
        action_status
        ;;
    stop)
        action_stop
        ;;
    *)
        echo "usage: $0 {plan|init|start-backend|start-frontend|status|stop} [--execute]"
        exit 2
        ;;
esac
