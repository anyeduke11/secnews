#!/usr/bin/env bash
# layout-backup.sh <stage-name>
# 在 backup/<stage>-<timestamp> 分支上快照当前工作树（含 uncommitted），然后回到原分支，工作树保持不变。
# 用法: ./scripts/layout-backup.sh stage-1-infra
set -euo pipefail

STAGE="${1:?用法: $0 <stage-name>}"
TS="$(date +%Y%m%d-%H%M%S)"
BACKUP_BRANCH="backup/${STAGE}-${TS}"
CURRENT="$(git rev-parse --abbrev-ref HEAD)"

git checkout -b "$BACKUP_BRANCH" -q
git add -A
if git diff --cached --quiet; then
  echo "[layout-backup] 工作树无改动，仅创建空快照分支 $BACKUP_BRANCH" >&2
  git commit -q --allow-empty -m "backup: ${STAGE} @ ${TS} (empty snapshot)"
else
  git commit -q -m "backup: ${STAGE} @ ${TS}"
fi
BACKUP_COMMIT="$(git rev-parse --short HEAD)"

# 回到原分支，并把快照内容恢复到工作树（保持与备份前一致）
git checkout -q "$CURRENT"
git restore --source="$BACKUP_BRANCH" --staged --worktree -- .
git reset -q

echo "[layout-backup] OK"
echo "  branch: $BACKUP_BRANCH"
echo "  commit: $BACKUP_COMMIT"
echo "  还原:  ./scripts/layout-restore.sh ${STAGE}"
