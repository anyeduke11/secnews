#!/usr/bin/env bash
# layout-restore.sh <stage-name|latest|list>
# 还原到指定 stage 备份：stash 当前工作，working tree 覆盖为备份内容，HEAD 不变。
# 用法:
#   ./scripts/layout-restore.sh stage-1-infra   # 还原到该 stage 最近一次备份
#   ./scripts/layout-restore.sh latest          # 还原到最近一次备份
#   ./scripts/layout-restore.sh list            # 列出所有备份
set -euo pipefail

ARG="${1:?用法: $0 <stage-name|latest|list>}"

if [ "$ARG" = "list" ]; then
  git for-each-ref --sort=-committerdate --format='%(refname:short)  %(committerdate:iso)  %(objectname:short)' 'refs/heads/backup/'
  exit 0
fi

if [ "$ARG" = "latest" ]; then
  BRANCH="$(git for-each-ref --sort=-committerdate --format='%(refname:short)' 'refs/heads/backup/' | head -1)"
else
  # 取该 stage 最近一次备份
  BRANCH="$(git for-each-ref --sort=-committerdate --format='%(refname:short)' "refs/heads/backup/${ARG}-*" | head -1)"
  # 兼容完整分支名（backup/xxx-时间戳）
  if [ -z "$BRANCH" ] && git show-ref --verify --quiet "refs/heads/${ARG}"; then
    BRANCH="$ARG"
  fi
fi

if [ -z "$BRANCH" ]; then
  echo "[layout-restore] 找不到匹配的备份: $ARG" >&2
  echo "可用备份:" >&2
  git for-each-ref --sort=-committerdate --format='  %(refname:short)' 'refs/heads/backup/' >&2
  exit 1
fi

echo "[layout-restore] 还原到: $BRANCH ($(git log -1 --format='%h %s' "$BRANCH"))"

# 1) stash 当前工作（含 untracked），可随时 git stash pop 找回
TS="$(date +%Y%m%d-%H%M%S)"
git stash push -u -m "pre-restore-snapshot-${TS}" >/dev/null 2>&1 || true

# 2) 工作树覆盖为备份内容
git restore --source="$BRANCH" --staged --worktree -- .

# 3) 删除 HEAD 中有、备份中没有的文件（保证工作树与备份完全一致）
comm -23 \
  <(git ls-tree -r --name-only HEAD | sort) \
  <(git ls-tree -r --name-only "$BRANCH" | sort) \
  | while IFS= read -r f; do rm -f "$f"; done

# 4) index 回到 HEAD（文件差异体现在 status 里）
git reset -q

echo "[layout-restore] OK — 工作树已还原，HEAD 仍在 $(git rev-parse --abbrev-ref HEAD)"
echo "  找回被覆盖的工作: git stash pop"
