#!/usr/bin/env bash
# execute_retirement.sh — hotspot 端 Phase 7 退役一键执行脚本。
#
# 文档: docs/HOTSPOT_RETIREMENT.md
# 上下文: SecNews_dsh_全栈整合_task-d12.md Phase 7
#
# 设计原则
# --------
# 1. **dry-run 默认**: 不传 --apply 时只打印会做什么, 不动文件/进程/git
# 2. **6 步流水线**: kill :8000 → 跑 export → 锁 baseline → git mv backend →
#    git mv frontend → git tag v0.5.0-retired
# 3. **safety checks**: 每步前检查前置条件 (lsof / git status / baseline)
# 4. **可分步**: --step N 只跑第 N 步 (用于排错或单步重跑)
# 5. **回滚指引**: 出错时打印 30 天应急回滚命令
#
# 用法
# ----
#   bash scripts/execute_retirement.sh                 # dry-run 全流程 (默认)
#   bash scripts/execute_retirement.sh --apply         # 真执行
#   bash scripts/execute_retirement.sh --step 2 --apply # 真执行第 2 步
#   bash scripts/execute_retirement.sh --skip-kill     # 跳过 step 1 (kill :8000)
#   bash scripts/execute_retirement.sh --no-export     # 跳过 step 2 (export_for_dsh)
#   bash scripts/execute_retirement.sh --help
#
# 前置条件
# --------
# - dsh-SecNews 端 secnews.db 行数已对账 (见 snapshot_for_retirement.py 的 dsh_verify_hint)
# - 当前 hotspot 端 git 工作树干净 (除了 untracked smoke artifact)
# - export_for_dsh.py 与 snapshot_for_retirement.py 已在 scripts/
#
# ⚠️  **破坏性**: --apply 之后 git mv 不可逆 (除非用 30 天应急回滚)

set -euo pipefail

# ---------- 路径 ----------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
HOTSPOT_DB="${REPO_ROOT}/backend/hotspot.db"
EXPORT_DIR="${REPO_ROOT}/data/export"
BASELINE_JSON="${REPO_ROOT}/data/retirement_baseline.json"
PYTHON_BIN="${PYTHON_BIN:-python3}"

# ---------- 默认参数 ----------
DRY_RUN=true
STEP=""            # 空=跑全部; 设数字=只跑该步
SKIP_KILL=false
SKIP_EXPORT=false
SKIP_BASELINE=false

# ---------- 颜色 ----------
if [[ -t 1 ]]; then
    RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
    BLUE='\033[0;34m'; BOLD='\033[1m'; RESET='\033[0m'
else
    RED=''; GREEN=''; YELLOW=''; BLUE=''; BOLD=''; RESET=''
fi

# ---------- 帮助 ----------
usage() {
    sed -n '2,30p' "${BASH_SOURCE[0]}" | sed 's/^# //; s/^#//'
    exit 0
}

# ---------- 参数解析 ----------
while [[ $# -gt 0 ]]; do
    case "$1" in
        --apply)        DRY_RUN=false; shift ;;
        --dry-run)      DRY_RUN=true; shift ;;
        --step)         STEP="$2"; shift 2 ;;
        --skip-kill)    SKIP_KILL=true; shift ;;
        --skip-export)  SKIP_EXPORT=true; shift ;;
        --skip-baseline) SKIP_BASELINE=true; shift ;;
        --help|-h)      usage ;;
        *)              echo "unknown arg: $1"; usage ;;
    esac
done

# ---------- 工具 ----------
banner() { echo -e "\n${BOLD}${BLUE}=== $1 ===${RESET}"; }
ok()     { echo -e "  ${GREEN}✓${RESET} $1"; }
warn()   { echo -e "  ${YELLOW}!${RESET} $1"; }
fail()   { echo -e "  ${RED}✗${RESET} $1"; exit 1; }
note()   { echo -e "  ${BLUE}·${RESET} $1"; }
run() {
    # run <cmd...>: dry-run 打印, apply 真执行
    if [[ "${DRY_RUN}" == true ]]; then
        echo -e "  ${YELLOW}[dry-run]${RESET} $*"
    else
        echo -e "  ${GREEN}[apply]${RESET}  $*"
        "$@"
    fi
}

should_run() {
    # should_run <step_num>: STEP 空=true; 否则 == step_num
    [[ -z "${STEP}" || "${STEP}" == "$1" ]]
}

# ---------- 前置检查 ----------
preflight() {
    banner "Preflight"
    cd "${REPO_ROOT}"

    note "REPO_ROOT:  ${REPO_ROOT}"
    note "DRY_RUN:    ${DRY_RUN}"
    note "STEP:       ${STEP:-<all>}"
    note "SKIP_KILL:  ${SKIP_KILL}, SKIP_EXPORT: ${SKIP_EXPORT}, SKIP_BASELINE: ${SKIP_BASELINE}"
    echo

    # 工作树干净 (允许 untracked, 但不允许 staged/unstaged 改动)
    if ! git diff --quiet HEAD 2>/dev/null; then
        warn "git working tree has uncommitted changes:"
        git status --short | sed 's/^/    /'
        if [[ "${DRY_RUN}" == false ]]; then
            fail "请先 git commit 或 git stash 后再 --apply"
        else
            warn "[dry-run] 继续, 但 --apply 会失败"
        fi
    else
        ok "git working tree clean"
    fi

    # hotspot.db 存在
    if [[ -f "${HOTSPOT_DB}" ]]; then
        ok "hotspot.db: $(du -h "${HOTSPOT_DB}" | cut -f1)"
    else
        warn "hotspot.db not found (step 1-2 会跳过)"
    fi

    # 关键工具
    command -v git >/dev/null && ok "git: $(git --version | awk '{print $3}')"
    command -v "${PYTHON_BIN}" >/dev/null && ok "${PYTHON_BIN}: $(${PYTHON_BIN} --version 2>&1 | awk '{print $2}')"
}

# ---------- Step 1: kill :8000 ----------
step1_kill() {
    banner "Step 1/6: 停 hotspot 端 :8000 进程"

    if [[ "${SKIP_KILL}" == true ]]; then
        warn "SKIP_KILL=true, 跳过"
        return 0
    fi

    if ! command -v lsof >/dev/null; then
        warn "lsof 不可用, 跳到手动 kill"
        note "请手动: ps aux | grep uvicorn | grep -v grep | awk '{print \$2}' | xargs kill"
        return 0
    fi

    local pids
    pids="$(lsof -ti:8000 2>/dev/null || true)"
    if [[ -z "${pids}" ]]; then
        ok ":8000 无占用, 跳过"
        return 0
    fi

    note "占用 :8000 的 PID: ${pids}"
    run bash -c "echo ${pids} | xargs kill -TERM"
    note "等 3 秒..."
    sleep 3

    local remain
    remain="$(lsof -ti:8000 2>/dev/null || true)"
    if [[ -n "${remain}" ]]; then
        warn "TERM 未生效, 升级 SIGKILL: ${remain}"
        run bash -c "echo ${remain} | xargs kill -KILL"
    else
        ok ":8000 已停止"
    fi
}

# ---------- Step 2: export_for_dsh.py 最后一次导出 ----------
step2_export() {
    banner "Step 2/6: 跑 export_for_dsh.py (最后一次导出, 入档)"

    if [[ "${SKIP_EXPORT}" == true ]]; then
        warn "SKIP_EXPORT=true, 跳过"
        return 0
    fi

    if [[ ! -f "${REPO_ROOT}/scripts/export_for_dsh.py" ]]; then
        fail "scripts/export_for_dsh.py 不存在"
    fi

    local archive="${REPO_ROOT}/data/export.archived-$(date +%Y%m%d-%H%M%S)"
    run mkdir -p "${REPO_ROOT}/data"
    if [[ "${DRY_RUN}" == false && -d "${EXPORT_DIR}" ]]; then
        run mv "${EXPORT_DIR}" "${archive}"
        note "旧 export 已归档到 ${archive}"
    fi

    run "${PYTHON_BIN}" "${REPO_ROOT}/scripts/export_for_dsh.py"
    ok "导出完成: ${EXPORT_DIR}/manifest.json"
}

# ---------- Step 3: snapshot baseline ----------
step3_baseline() {
    banner "Step 3/6: 锁定 retirement baseline"

    if [[ "${SKIP_BASELINE}" == true ]]; then
        warn "SKIP_BASELINE=true, 跳过"
        return 0
    fi

    if [[ ! -f "${REPO_ROOT}/scripts/snapshot_for_retirement.py" ]]; then
        fail "scripts/snapshot_for_retirement.py 不存在"
    fi

    run "${PYTHON_BIN}" "${REPO_ROOT}/scripts/snapshot_for_retirement.py"

    if [[ "${DRY_RUN}" == false ]]; then
        if [[ ! -f "${BASELINE_JSON}" ]]; then
            fail "baseline 没生成: ${BASELINE_JSON}"
        fi
        ok "baseline: ${BASELINE_JSON}"
    fi
}

# ---------- Step 4: git mv backend ----------
step4_mv_backend() {
    banner "Step 4/6: git mv backend hotspot-archived"

    if [[ -d "${REPO_ROOT}/hotspot-archived/backend" ]]; then
        warn "hotspot-archived/backend 已存在, 跳过"
        return 0
    fi

    run git mv backend hotspot-archived/backend
    note "git history 保留 (git log --follow hotspot-archived/backend)"
}

# ---------- Step 5: git mv frontend ----------
step5_mv_frontend() {
    banner "Step 5/6: git mv frontend hotspot-archived/frontend"

    if [[ -d "${REPO_ROOT}/hotspot-archived/frontend" ]]; then
        warn "hotspot-archived/frontend 已存在, 跳过"
        return 0
    fi

    if [[ ! -d "${REPO_ROOT}/frontend" ]]; then
        warn "frontend/ 不存在 (可能已 dsh 端接管?), 跳过"
        return 0
    fi

    run git mv frontend hotspot-archived/frontend
}

# ---------- Step 6: git tag v0.5.0-retired ----------
step6_tag() {
    banner "Step 6/6: git tag v0.5.0-retired"

    if git rev-parse v0.5.0-retired >/dev/null 2>&1; then
        warn "tag v0.5.0-retired 已存在, 跳过"
        return 0
    fi

    local msg="Python 后端退役标记, 数据已迁入 dsh-SecNews

详见 docs/HOTSPOT_RETIREMENT.md
Phase 7 完成: hotspot.db 8 表 8902 行 + wiki 4245 文件
baseline: data/retirement_baseline.json
迁移脚本: scripts/export_for_dsh.py + dsh packages/store/src/migrate-from-hotspot.ts"
    run git tag -a v0.5.0-retired -m "${msg}"
    note "之后可用 git push origin v0.5.0-retired 发布"
}

# ---------- 应急回滚指引 ----------
rollback_hint() {
    banner "30 天应急回滚 (SLA)"
    cat <<EOF
  dsh 端若有严重问题, 可在 30 天内回滚到 hotspot:
    1. cd hotspot
    2. git checkout hotspot-archived/backend hotspot-archived/frontend \\
         -- backend frontend  # 从 tag 还原目录
    3. python run.py                                    # :8000 重启
    4. python scripts/snapshot_for_retirement.py --verify # 校 baseline

  注: hotspot-archived/ 保留全量 git history, --follow 可追踪原文件改动。
EOF
}

# ---------- 主流程 ----------
main() {
    preflight

    should_run 1 && step1_kill
    should_run 2 && step2_export
    should_run 3 && step3_baseline
    should_run 4 && step4_mv_backend
    should_run 5 && step5_mv_frontend
    should_run 6 && step6_tag

    echo
    if [[ "${DRY_RUN}" == true ]]; then
        banner "[dry-run 完成] 上面所有 [dry-run] 步骤都没真执行"
        echo "  真执行请加 --apply:"
        echo "    bash scripts/execute_retirement.sh --apply"
    else
        banner "[apply 完成]"
        echo "  git status --short 应该空 (除了 tag / git mv 后的 hotspot-archived)"
        echo "  git tag 应该列出 v0.5.0-retired"
        echo "  hotspot.db 与 data/export/ 已 gitignored 保留在 disk (不删, 30 天回滚保险)"
    fi
    echo
    rollback_hint
}

main
