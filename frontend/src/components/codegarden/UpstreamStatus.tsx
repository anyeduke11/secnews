// frontend/src/components/codegarden/UpstreamStatus.tsx
import { CgProject } from '../../types/codegarden';

interface UpstreamStatusProps {
  project: CgProject;
  onSync: () => void;
}

export function UpstreamStatus({ project, onSync }: UpstreamStatusProps) {
  const behind = project.commits_behind;
  const ahead = project.commits_ahead;
  const lastSync = project.last_synced_at
    ? new Date(project.last_synced_at).toLocaleString()
    : '从未同步';

  const status = behind === 0
    ? { label: '已同步', color: '#00c96a' }
    : behind <= 10
    ? { label: `${behind} commits 落后`, color: '#f0c929' }
    : { label: `${behind} commits 严重落后`, color: '#e85d5d' };

  return (
    <div
      className="rounded-[var(--radius-sm)] p-2.5 mb-2"
      style={{ backgroundColor: 'var(--bg-hover)', border: '1px solid var(--border-color)' }}
    >
      <div className="flex items-center justify-between mb-1.5">
        <div className="text-[10px] font-semibold" style={{ color: 'var(--text-muted)' }}>
          上游同步状态
        </div>
        <button
          onClick={onSync}
          className="text-[10px] px-2 py-0.5 rounded"
          style={{ border: '1px solid var(--border-color)', color: 'var(--color-ai)' }}
        >
          立即同步
        </button>
      </div>
      <div className="grid grid-cols-2 gap-2 text-[10px]">
        <div>
          <span style={{ color: 'var(--text-muted)' }}>状态: </span>
          <span style={{ color: status.color }}>{status.label}</span>
        </div>
        <div>
          <span style={{ color: 'var(--text-muted)' }}>默认分支: </span>
          <span className="font-mono" style={{ color: 'var(--text-primary)' }}>
            {project.upstream_default_branch || '-'}
          </span>
        </div>
        <div>
          <span style={{ color: 'var(--text-muted)' }}>落后: </span>
          <span className="font-mono" style={{ color: behind > 0 ? '#e85d5d' : 'var(--text-primary)' }}>{behind}</span>
        </div>
        <div>
          <span style={{ color: 'var(--text-muted)' }}>领先: </span>
          <span className="font-mono" style={{ color: ahead > 0 ? '#00c96a' : 'var(--text-primary)' }}>{ahead}</span>
        </div>
        <div className="col-span-2">
          <span style={{ color: 'var(--text-muted)' }}>最后同步: </span>
          <span style={{ color: 'var(--text-secondary)' }}>{lastSync}</span>
        </div>
        <div className="col-span-2">
          <span style={{ color: 'var(--text-muted)' }}>upstream: </span>
          {project.upstream_url ? (
            <a href={project.upstream_url} target="_blank" rel="noreferrer" className="hover:underline font-mono" style={{ color: 'var(--color-ai)' }}>
              {project.upstream_url.replace('https://github.com/', '')}
            </a>
          ) : (
            <span style={{ color: 'var(--text-muted)' }}>-</span>
          )}
        </div>
      </div>
    </div>
  );
}
