/**
 * DepList — 依赖列表（卡片网格 + 单条删除 + 影响分析）。
 *
 * Phase 1B: 拆自原 DependencyGraph.tsx 列表段。
 * props-only: 接收 dependencies + onRemove + onImpact, 每张卡片含:
 *  - 类型/源/目标/删除/影响分析 按钮
 */
import { DepListProps } from './types';
import { DEP_TYPE_COLORS, DEP_TYPE_LABELS } from './types';

export function DepList({ dependencies, onRemove, onImpact }: DepListProps) {
  return (
    <div className="mt-3">
      <div className="text-[11px] mb-1.5" style={{ color: 'var(--text-muted)' }}>
        所有依赖
      </div>
      <div
        className="grid gap-1.5"
        style={{ gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))' }}
      >
        {dependencies.map((d) => (
          <div
            key={d.id}
            className="rounded p-2 text-[10px]"
            style={{
              backgroundColor: 'var(--bg-elevated)',
              border: '1px solid var(--border-color)',
            }}
          >
            <div className="flex items-center justify-between mb-1">
              <span style={{ color: DEP_TYPE_COLORS[d.dep_type] }}>
                {DEP_TYPE_LABELS[d.dep_type]}
              </span>
              <button
                onClick={async () => {
                  try {
                    await onRemove(d.id);
                  } catch (e: any) {
                    window.alert(e?.message || String(e));
                  }
                }}
                className="text-[9px]"
                style={{ color: '#e85d5d' }}
              >
                删除
              </button>
            </div>
            <div className="font-mono" style={{ color: 'var(--text-primary)' }}>
              {d.source_type}:{d.source_id}
            </div>
            <div style={{ color: 'var(--text-muted)' }}>↓</div>
            <div className="font-mono" style={{ color: 'var(--text-primary)' }}>
              {d.target_type}:{d.target_id}
            </div>
            <button
              onClick={() => onImpact(d.target_type, d.target_id)}
              className="mt-1.5 text-[9px] w-full py-0.5 rounded"
              style={{ border: '1px solid var(--border-color)', color: 'var(--color-ai)' }}
            >
              影响分析
            </button>
          </div>
        ))}
      </div>
    </div>
  );
}
