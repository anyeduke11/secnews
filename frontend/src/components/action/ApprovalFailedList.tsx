/**
 * ApprovalFailedList — 审批收件箱「失败 · 可重试」区块 (B5 从 ApprovalInbox 抽出)
 *
 * 纯展示 + props 回调: 失败提案展示模型失败原因, 有 case 锚点才允许一键重试
 * (重试写操作仍由容器 ApprovalInbox 编排); DOM / class / data-testid 逐字一致。
 */
import type { Proposal } from '../../api/proposals';
import { Badge } from './ApprovalBadge';
import { KIND_LABEL } from './approvalModel';

interface ApprovalFailedListProps {
  failed: Proposal[];
  /** 正在重新起草的提案 id (null = 空闲) */
  retrying: string | null;
  onRetry: (p: Proposal) => void;
}

export function ApprovalFailedList({ failed, retrying, onRetry }: ApprovalFailedListProps) {
  return (
    <>
      <h4 className="text-xs font-semibold mb-2" style={{ color: 'var(--sn-ink, var(--text-primary))' }}>
        失败 · 可重试 ({failed.length})
      </h4>
      <ul className="grid grid-cols-1 lg:grid-cols-2 gap-2">
        {failed.map(p => (
          <li key={p.id} className="p-3 rounded border"
            style={{ borderColor: 'var(--sn-line, var(--line))' }}
            data-testid="approval-failed-card">
            <div className="flex flex-wrap items-center gap-2">
              <Badge tone="gray">{KIND_LABEL[p.kind] ?? p.kind}</Badge>
              {p.case_id && (
                <span className="text-xs num" style={{ color: 'var(--sn-ink-3, var(--text-muted))' }}>{p.case_id}</span>
              )}
              <span className="text-xs ml-auto" style={{ color: 'var(--sn-red, var(--color-error))' }}>
                模型未完成
              </span>
            </div>
            <p className="text-xs mt-2 break-words" style={{ color: 'var(--sn-ink, var(--text-primary))' }}>
              {p.error_msg || '(无错误信息)'}
            </p>
            <button
              type="button"
              className="text-xs mt-2 px-2.5 py-1 rounded font-medium focus-ring disabled:opacity-50"
              disabled={!p.case_id || retrying !== null}
              title={p.case_id ? '用原案件重新 AI 起草' : '该失败提案无案件锚点, 无法重试'}
              onClick={() => { onRetry(p); }}
              style={{ border: '1px solid var(--sn-line, var(--line))', color: 'var(--sn-ink, var(--text-primary))' }}
              data-testid="retry-btn"
            >
              {retrying === p.id ? '重新起草中…' : '重试起草'}
            </button>
          </li>
        ))}
      </ul>
    </>
  );
}
