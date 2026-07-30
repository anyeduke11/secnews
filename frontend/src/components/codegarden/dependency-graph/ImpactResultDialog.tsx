/**
 * ImpactResultDialog — 影响分析结果弹窗（BFS 反向追溯结果列表）。
 *
 * Phase 1B: 拆自原 DependencyGraph.tsx 影响分析弹窗段。
 * props-only: 接收 result 列表 + onClose 回调, 渲染每条依赖 + depth 标记。
 */
import { CgDependency } from '../../../types/codegarden';
import { Icon } from '../../Icon';
import { ImpactResultDialogProps, DEP_TYPE_COLORS, DEP_TYPE_LABELS } from './types';

export function ImpactResultDialog({ result, onClose }: ImpactResultDialogProps) {
  return (
    <div
      className="fixed inset-0 z-50 flex items-end sm:items-center justify-center p-4"
      style={{ backgroundColor: 'var(--bg-overlay)' }}
      onClick={onClose}
    >
      <div
        className="tech-modal w-full max-w-md max-h-[80vh] overflow-y-auto p-3"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between mb-2">
          <h3 className="text-sm font-bold flex items-center gap-2" style={{ color: 'var(--text-primary)' }}>
            <Icon size={16}>
              <circle cx="12" cy="12" r="10" />
              <line x1="22" y1="12" x2="18" y2="12" />
              <line x1="6" y1="12" x2="2" y2="12" />
              <line x1="12" y1="6" x2="12" y2="2" />
              <line x1="12" y1="22" x2="12" y2="18" />
            </Icon>
            影响分析结果 ({result.length})
          </h3>
          <button onClick={onClose} className="btn-ghost px-2 py-1 text-[11px]" aria-label="关闭">
            <Icon size={14}>
              <line x1="18" y1="6" x2="6" y2="18" />
              <line x1="6" y1="6" x2="18" y2="18" />
            </Icon>
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
