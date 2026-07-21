// frontend/src/components/codegarden/ProjectList.tsx
import {
  CgProject,
  LifecycleStage,
  LIFECYCLE_COLORS,
  LIFECYCLE_LABELS,
  SOURCE_TYPE_LABELS,
} from '../../types/codegarden';

interface ProjectListProps {
  items: CgProject[];
  selectedIds: Set<string>;
  onSelect?: (p: CgProject) => void;
  onToggleSelect: (id: string) => void;
  onToggleAll: () => void;
  onTransition?: (id: string, to: LifecycleStage) => void;
}

const NEXT_STAGE: Partial<Record<LifecycleStage, LifecycleStage>> = {
  ideation: 'prototype',
  prototype: 'development',
  development: 'testing',
  testing: 'running',
  running: 'maintenance',
};

function formatDate(s?: string | null): string {
  if (!s) return '-';
  try {
    const d = new Date(s);
    return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
  } catch {
    return s.slice(0, 10);
  }
}

export function ProjectList({
  items, selectedIds, onSelect, onToggleSelect, onToggleAll, onTransition,
}: ProjectListProps) {
  const allSelected = items.length > 0 && items.every(p => selectedIds.has(p.id));
  const someSelected = items.some(p => selectedIds.has(p.id));
  const headerChecked = allSelected;
  const headerIndeterminate = !allSelected && someSelected;

  return (
    <div
      className="rounded-[var(--radius-sm)] overflow-hidden"
      style={{ border: '1px solid var(--border-color)' }}
    >
      <table className="w-full text-[11px]" style={{ backgroundColor: 'var(--bg-elevated)' }}>
        <thead>
          <tr style={{ backgroundColor: 'var(--bg-hover)', borderBottom: '1px solid var(--border-color)' }}>
            <th className="w-8 py-2 px-2 text-left">
              <input
                type="checkbox"
                checked={headerChecked}
                ref={el => { if (el) el.indeterminate = headerIndeterminate; }}
                onChange={onToggleAll}
                aria-label="全选"
                style={{ cursor: 'pointer' }}
              />
            </th>
            <th className="py-2 px-2 text-left font-semibold" style={{ color: 'var(--text-secondary)' }}>项目</th>
            <th className="py-2 px-2 text-left font-semibold" style={{ color: 'var(--text-secondary)' }}>状态</th>
            <th className="py-2 px-2 text-left font-semibold" style={{ color: 'var(--text-secondary)' }}>类型</th>
            <th className="py-2 px-2 text-left font-semibold" style={{ color: 'var(--text-secondary)' }}>来源</th>
            <th className="py-2 px-2 text-left font-semibold" style={{ color: 'var(--text-secondary)' }}>技术栈</th>
            <th className="py-2 px-2 text-left font-semibold" style={{ color: 'var(--text-secondary)' }}>落后</th>
            <th className="py-2 px-2 text-left font-semibold" style={{ color: 'var(--text-secondary)' }}>最近活动</th>
            <th className="w-20 py-2 px-2 text-right font-semibold" style={{ color: 'var(--text-secondary)' }}>操作</th>
          </tr>
        </thead>
        <tbody>
          {items.map((p, idx) => {
            const accent = LIFECYCLE_COLORS[p.lifecycle_stage];
            const isSelected = selectedIds.has(p.id);
            const next = NEXT_STAGE[p.lifecycle_stage];
            return (
              <tr
                key={p.id}
                style={{
                  borderTop: idx === 0 ? 'none' : '1px solid var(--border-color)',
                  backgroundColor: isSelected ? 'var(--bg-hover)' : 'transparent',
                }}
                onClick={() => onSelect?.(p)}
                className="cursor-pointer"
              >
                <td className="py-2 px-2" onClick={(e) => e.stopPropagation()}>
                  <input
                    type="checkbox"
                    checked={isSelected}
                    onChange={() => onToggleSelect(p.id)}
                    aria-label={`选择 ${p.name}`}
                    style={{ cursor: 'pointer' }}
                  />
                </td>
                <td className="py-2 px-2">
                  <div className="flex items-center gap-2">
                    <span
                      className="w-0.5 h-4 rounded shrink-0"
                      style={{ backgroundColor: accent }}
                      aria-hidden="true"
                    />
                    <span
                      className="font-semibold truncate"
                      style={{ color: 'var(--text-primary)' }}
                      title={p.name}
                    >
                      {p.display_name || p.name}
                    </span>
                  </div>
                </td>
                <td className="py-2 px-2">
                  <span
                    className="text-[10px] px-1.5 py-0.5 rounded"
                    style={{ backgroundColor: accent + '20', color: accent }}
                  >
                    {LIFECYCLE_LABELS[p.lifecycle_stage]}
                  </span>
                </td>
                <td className="py-2 px-2 font-mono" style={{ color: 'var(--text-secondary)' }}>{p.type}</td>
                <td className="py-2 px-2" style={{ color: 'var(--text-secondary)' }}>
                  {SOURCE_TYPE_LABELS[p.source_type]}
                </td>
                <td className="py-2 px-2" style={{ color: 'var(--text-muted)' }}>
                  {p.tech_stack.length > 0 ? p.tech_stack.slice(0, 3).join(', ') + (p.tech_stack.length > 3 ? '…' : '') : '-'}
                </td>
                <td className="py-2 px-2 font-mono" style={{ color: p.commits_behind > 0 ? 'var(--color-error)' : 'var(--text-muted)' }}>
                  {p.source_type === 'fork' && p.commits_behind > 0 ? `↓${p.commits_behind}` : '-'}
                </td>
                <td className="py-2 px-2 font-mono" style={{ color: 'var(--text-muted)' }}>
                  {formatDate(p.last_activity_at)}
                </td>
                <td className="py-2 px-2 text-right" onClick={(e) => e.stopPropagation()}>
                  {next && onTransition && (
                    <button
                      onClick={() => onTransition(p.id, next)}
                      className="text-[10px] px-2 py-0.5 rounded"
                      style={{ border: '1px solid var(--border-color)', color: 'var(--text-secondary)' }}
                      title={`推进到 ${LIFECYCLE_LABELS[next]}`}
                    >
                      → {LIFECYCLE_LABELS[next]}
                    </button>
                  )}
                </td>
              </tr>
            );
          })}
          {items.length === 0 && (
            <tr>
              <td colSpan={9} className="py-6 text-center" style={{ color: 'var(--text-muted)' }}>
                空
              </td>
            </tr>
          )}
        </tbody>
      </table>
    </div>
  );
}
