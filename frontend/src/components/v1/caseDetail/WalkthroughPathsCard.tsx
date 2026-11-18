/**
 * WalkthroughPathsCard — 「走查 3 路径」指示卡 (T12 强化: 显式呈现 3 路径而非简单色块)
 * (B5 续拆: 自 CaseDetail.tsx 原样搬运, DOM/class 逐字不变; 4 个标记经 caseDetailModel 纯函数派生)
 */
import type { Action, Run, Artifact } from '../../../api/v1';
import { Badge } from './CaseBadge';
import { walkthroughFlags } from './caseDetailModel';

export function WalkthroughPathsCard({ actions, runs, artifacts }: { actions: Action[]; runs: Run[]; artifacts: Artifact[] }) {
  const { hasMissingAssets, hasFailure, hasPendingAcceptance, hasRejected } = walkthroughFlags(actions, runs, artifacts);
  return (
    <div className="p-3 rounded-lg border" style={{ background: 'var(--bg-muted)', borderColor: 'var(--line)' }}>
      <div className="flex items-center gap-3 flex-wrap">
        <span className="text-sm font-medium" style={{ color: 'var(--text-primary)' }}>走查 3 路径:</span>
        {hasMissingAssets && <Badge color="yellow">缺资产 (材料生成 ≠ 排查完成)</Badge>}
        {hasPendingAcceptance && <Badge color="blue">待验收</Badge>}
        {hasFailure && <Badge color="red">失败</Badge>}
        {hasRejected && <Badge color="red">已拒绝 (防重传蒙混 §8.3)</Badge>}
        {!hasMissingAssets && !hasPendingAcceptance && !hasFailure && !hasRejected && (
          <span className="text-sm" style={{ color: 'var(--text-muted)' }}>无异常</span>
        )}
      </div>
      <div className="text-xs mt-2" style={{ color: 'var(--text-muted)' }}>
        {actions.length} 个行动 · {runs.length} 次运行 · {artifacts.length} 个产物
        {artifacts.filter(a => a.status === 'accepted').length > 0 && ` · ${artifacts.filter(a => a.status === 'accepted').length} 已业务验收`}
      </div>
    </div>
  );
}
