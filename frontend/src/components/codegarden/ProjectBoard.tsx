// frontend/src/components/codegarden/ProjectBoard.tsx
import { useMemo } from 'react';
import { CgProject, LifecycleStage, LIFECYCLE_LABELS, LIFECYCLE_COLORS } from '../../types/codegarden';
import { ProjectCard } from './ProjectCard';

const COLUMN_STAGES: LifecycleStage[] = [
  'ideation', 'prototype', 'development', 'testing', 'running', 'maintenance',
];

interface ProjectBoardProps {
  items: CgProject[];
  onSelect?: (p: CgProject) => void;
  onTransition?: (id: string, to: LifecycleStage) => void;
}

export function ProjectBoard({ items, onSelect, onTransition }: ProjectBoardProps) {
  const grouped = useMemo(() => {
    const map: Record<LifecycleStage, CgProject[]> = {
      ideation: [], prototype: [], development: [], testing: [],
      running: [], maintenance: [], archived: [], deprecated: [],
    };
    for (const it of items) {
      if (map[it.lifecycle_stage]) map[it.lifecycle_stage].push(it);
    }
    return map;
  }, [items]);

  return (
    <div
      className="grid gap-3 overflow-x-auto pb-2"
      style={{ gridTemplateColumns: `repeat(${COLUMN_STAGES.length}, 220px)` }}
    >
      {COLUMN_STAGES.map(stage => (
        <div key={stage} className="flex flex-col gap-2">
          <div className="flex items-center justify-between px-2 py-1.5 rounded-[var(--radius-sm)]" style={{ backgroundColor: 'var(--bg-hover)' }}>
            <span className="text-xs font-semibold" style={{ color: LIFECYCLE_COLORS[stage] }}>
              {LIFECYCLE_LABELS[stage]}
            </span>
            <span className="text-[10px] font-mono" style={{ color: 'var(--text-muted)' }}>
              {grouped[stage].length}
            </span>
          </div>
          <div className="flex flex-col gap-2 min-h-[120px]">
            {grouped[stage].map(p => (
              <ProjectCard
                key={p.id}
                project={p}
                onClick={() => onSelect?.(p)}
                onTransition={onTransition}
              />
            ))}
            {grouped[stage].length === 0 && (
              <div
                className="text-[10px] text-center py-3 rounded-[var(--radius-sm)]"
                style={{ color: 'var(--text-muted)', border: '1px dashed var(--border-color)' }}
              >
                空
              </div>
            )}
          </div>
        </div>
      ))}
    </div>
  );
}
