/**
 * CaseDetailHeader — 头部 (标题/状态/优先级/close 按钮) + 加载·错误·已加载提示条
 * (B5 续拆: 自 CaseDetail.tsx 原样搬运, DOM/class/data-testid 逐字不变)
 *
 * C10 R14/R17: close 按钮走 allowed_actions 守卫, 由容器决定可见性与 disabled 态。
 */
import type { Case } from '../../../domain/v1_0';
import { Badge } from './CaseBadge';

interface Props {
  display: Case;
  loading: boolean;
  error: string | null;
  pendingMutation: string | null;
  onBack: () => void;
  onCloseCase: () => void;
}

export function CaseDetailHeader({ display, loading, error, pendingMutation, onBack, onCloseCase }: Props) {
  return (
    <>
      {/* 头部 */}
      <div className="flex items-start justify-between">
        <div>
          <button onClick={onBack} className="text-sm mb-2" style={{ color: 'var(--text-muted)' }}>← 返回事项列表</button>
          <h2 className="text-xl font-bold" style={{ color: 'var(--text-primary)' }}>{display.title}</h2>
          <div className="text-sm mt-1" style={{ color: 'var(--text-muted)' }}>{display.question}</div>
          <div className="text-xs font-mono mt-1" style={{ color: 'var(--text-muted)' }}>
            {display.id} · rev {display.revision}
            {display.reason && ` · ${display.reason}`}
          </div>
        </div>
        <div className="flex gap-2 items-center">
          <Badge color={display.status === 'open' ? 'blue' : display.status === 'in_progress' ? 'green' : display.status === 'blocked' ? 'yellow' : 'gray'}>{display.status}</Badge>
          <Badge color={display.priority === 'p0' ? 'red' : display.priority === 'p1' ? 'yellow' : 'gray'}>{display.priority}</Badge>
          {/* C10 R14/R17: close 按钮 (走 allowed_actions 守卫, R17 4 守卫后端已落) */}
          {display.allowed_actions?.includes('close' as any) && (
            <button
              onClick={onCloseCase}
              disabled={pendingMutation === `close:${display.id}`}
              className="text-xs px-3 py-1.5 rounded font-medium focus-ring disabled:opacity-50"
              style={{ background: 'var(--color-warning)', color: 'var(--text-on-warning, #fff)' }}
              data-testid="close-case-btn"
            >
              {pendingMutation === `close:${display.id}` ? '关闭中…' : '关闭事项'}
            </button>
          )}
        </div>
      </div>

      {/* T08 加载 / 错误 / fallback 提示 */}
      {loading && (
        <div className="p-3 rounded-lg border text-sm" style={{ background: 'var(--bg-muted)', borderColor: 'var(--line)', color: 'var(--text-muted)' }}>
          加载中...
        </div>
      )}
      {error && !loading && (
        <div className="p-3 rounded-lg border text-sm" style={{ background: 'var(--bg-warning)', borderColor: 'var(--color-warning)', color: 'var(--color-warning)' }}>
          API 调用失败, 显示列表缓存数据: {error}
        </div>
      )}
      {!loading && !error && (
        <div className="p-3 rounded-lg border text-sm" style={{ background: 'var(--bg-card)', borderColor: 'var(--line)', color: 'var(--text-muted)' }}>
          已加载后端数据 · revision {display.revision} · allowed_actions: {display.allowed_actions?.join(', ') || '(none)'}
        </div>
      )}
    </>
  );
}
