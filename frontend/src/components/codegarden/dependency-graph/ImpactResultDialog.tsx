/**
 * ImpactResultDialog — 影响分析结果弹窗（BFS 反向追溯结果列表）。
 *
 * Phase 1B: 拆自原 DependencyGraph.tsx 影响分析弹窗段。
 * props-only: 接收 result 列表 + onClose 回调, 渲染每条依赖 + depth 标记。
 */
import { CgDependency } from '../../../types/codegarden';
import { ImpactResultDialogProps, DEP_TYPE_COLORS, DEP_TYPE_LABELS } from './types';

export function ImpactResultDialog({ result, onClose }: ImpactResultDialogProps) {
  return (
    <div
      className="fixed inset-0 z-50 flex items-end sm:items-center justify-center p-4"
      style={{ backgroundColor: 'var(--bg-overlay)' }}
      onClick={onClose}
    >
      <div
        className="w-full max-w-md max-h-[80vh] overflow-y-auto rounded-[var(--radius-md)] p-3"
        style={{
          backgroundColor: 'var(--bg-elevated)',
          border: '1px solid var(--border-color)',
        }}
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between mb-2">
          <span className="text-sm font-bold" style={{ color: 'var(--text-primary)' }}>
            影响分析结果 ({result.length})
          </span>
          <button onClick={onClose} className="btn-ghost px-2 py-1 text-[11px]">
            ✕
          </button>
        </div>
        {result.length === 0 ? (
          <div
            className="text-[11px] text-center py-3"
            style={{ color: 'var(--text-muted)' }}
          >
            无上游依赖
          </div>
        ) : (
          <div className="space-y-1.5">
            {result.map((d: CgDependency) => (
              <div
                key={d.id}
                className="rounded p-2 text-[10px]"
                style={{
                  backgroundColor: 'var(--bg-hover)',
                  border: '1px solid var(--border-color)',
                }}
              >
                <div className="flex items-center justify-between mb-1">
                  <span style={{ color: DEP_TYPE_COLORS[d.dep_type] }}>
                    {DEP_TYPE_LABELS[d.dep_type]}
                  </span>
                  {d._depth !== undefined && (
                    <span className="font-mono" style={{ color: 'var(--text-muted)' }}>
                      depth={d._depth}
                    </span>
                  )}
                </div>
                <div className="font-mono" style={{ color: 'var(--text-primary)' }}>
                  {d.source_type}:{d.source_id} → {d.target_type}:{d.target_id}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
