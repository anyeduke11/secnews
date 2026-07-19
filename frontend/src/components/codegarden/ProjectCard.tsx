// frontend/src/components/codegarden/ProjectCard.tsx
import {
  CgProject,
  LifecycleStage,
  LIFECYCLE_COLORS,
  LIFECYCLE_LABELS,
  SOURCE_TYPE_LABELS,
} from '../../types/codegarden';

interface ProjectCardProps {
  project: CgProject;
  onClick?: () => void;
  onTransition?: (id: string, to: LifecycleStage) => void;
}

const NEXT_STAGE: Partial<Record<LifecycleStage, LifecycleStage>> = {
  ideation: 'prototype',
  prototype: 'development',
  development: 'testing',
  testing: 'running',
  running: 'maintenance',
};

export function ProjectCard({ project, onClick, onTransition }: ProjectCardProps) {
  const accent = LIFECYCLE_COLORS[project.lifecycle_stage];
  const next = NEXT_STAGE[project.lifecycle_stage];
  const behind = project.commits_behind;

  return (
    <div
      onClick={onClick}
      className="rounded-[var(--radius-sm)] p-2.5 cursor-pointer transition-colors"
      style={{
        backgroundColor: 'var(--bg-elevated)',
        border: '1px solid var(--border-color)',
        borderLeft: `3px solid ${accent}`,
      }}
    >
      <div className="flex items-start justify-between gap-2">
        <div className="flex-1 min-w-0">
          <div className="text-xs font-semibold truncate" style={{ color: 'var(--text-primary)' }} title={project.name}>
            {project.display_name || project.name}
          </div>
          {project.description && (
            <div className="text-[10px] mt-0.5 line-clamp-2" style={{ color: 'var(--text-muted)' }}>
              {project.description}
            </div>
          )}
        </div>
        <span
          className="shrink-0 text-[9px] px-1.5 py-0.5 rounded"
          style={{ backgroundColor: accent + '20', color: accent }}
        >
          {LIFECYCLE_LABELS[project.lifecycle_stage]}
        </span>
      </div>

      <div className="flex items-center gap-1.5 mt-2 flex-wrap">
        <span className="text-[9px] px-1.5 py-0.5 rounded" style={{ backgroundColor: 'var(--bg-hover)', color: 'var(--text-secondary)' }}>
          {SOURCE_TYPE_LABELS[project.source_type]}
        </span>
        <span className="text-[9px] px-1.5 py-0.5 rounded" style={{ backgroundColor: 'var(--bg-hover)', color: 'var(--text-secondary)' }}>
          {project.type}
        </span>
        {project.source_type === 'fork' && behind > 0 && (
          <span
            className="text-[9px] px-1.5 py-0.5 rounded font-mono"
            style={{ backgroundColor: '#e85d5d20', color: '#e85d5d' }}
            title={`落后上游 ${behind} commits`}
          >
            ↓{behind}
          </span>
        )}
        {project.health_score > 0 && (
          <span className="text-[9px] font-mono" style={{ color: 'var(--text-muted)' }}>
            ❤ {project.health_score}
          </span>
        )}
      </div>

      {next && onTransition && (
        <button
          onClick={(e) => { e.stopPropagation(); onTransition(project.id, next); }}
          className="mt-2 text-[9px] w-full py-0.5 rounded"
          style={{ border: '1px solid var(--border-color)', color: 'var(--text-secondary)' }}
          title={`推进到 ${LIFECYCLE_LABELS[next]}`}
        >
          → {LIFECYCLE_LABELS[next]}
        </button>
      )}
    </div>
  );
}
