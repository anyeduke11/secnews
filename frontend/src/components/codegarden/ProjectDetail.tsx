// frontend/src/components/codegarden/ProjectDetail.tsx
import { useEffect, useState, ReactNode } from 'react';
import {
  CgProject,
  CgProjectActivity,
  CgProjectStage,
  LifecycleStage,
  LIFECYCLE_COLORS,
  LIFECYCLE_LABELS,
} from '../../types/codegarden';
import { UpstreamStatus } from './UpstreamStatus';

interface ProjectDetailProps {
  project: CgProject;
  onClose: () => void;
  onTransition: (id: string, to: LifecycleStage) => Promise<CgProject>;
  onSync: (id: string) => Promise<{ task_id: number }>;
}

const ALL_STAGES: LifecycleStage[] = [
  'ideation', 'prototype', 'development', 'testing', 'running', 'maintenance', 'archived', 'deprecated',
];

export function ProjectDetail({ project, onClose, onTransition, onSync }: ProjectDetailProps) {
  const [activities, setActivities] = useState<CgProjectActivity[]>([]);
  const [stages, setStages] = useState<CgProjectStage[]>([]);
  const [loading, setLoading] = useState(true);
  const [toast, setToast] = useState<{ kind: 'ok' | 'err'; msg: string } | null>(null);

  const flash = (kind: 'ok' | 'err', msg: string) => {
    setToast({ kind, msg });
    setTimeout(() => setToast(null), 3000);
  };

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    Promise.all([
      fetch(`/api/codegarden/projects/${project.id}/activities`).then(r => r.json()),
      fetch(`/api/codegarden/projects/${project.id}/timeline`).then(r => r.json()),
    ])
      .then(([a, s]) => {
        if (cancelled) return;
        // 修复 spec bug: API 返回 {activities: [...]} / {stages: [...]} (非 items)
        setActivities(a.activities || []);
        setStages(s.stages || []);
      })
      .catch(e => flash('err', `加载详情失败: ${e?.message || e}`))
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [project.id]);

  const handleTransition = async (to: LifecycleStage) => {
    try {
      await onTransition(project.id, to);
      flash('ok', `已切换到 ${LIFECYCLE_LABELS[to]}`);
    } catch (e: any) {
      flash('err', e?.message || String(e));
    }
  };

  const handleSync = async () => {
    try {
      const { task_id } = await onSync(project.id);
      flash('ok', `已触发同步 (task #${task_id})`);
    } catch (e: any) {
      flash('err', e?.message || String(e));
    }
  };

  const accent = LIFECYCLE_COLORS[project.lifecycle_stage];

  return (
    <div
      className="fixed inset-0 z-50 flex items-end sm:items-center justify-center p-4"
      style={{ backgroundColor: 'rgba(0,0,0,0.5)' }}
      onClick={onClose}
    >
      <div
        className="w-full max-w-2xl max-h-[90vh] overflow-y-auto rounded-[var(--radius-md)] p-4"
        style={{ backgroundColor: 'var(--bg-elevated)', border: '1px solid var(--border-color)' }}
        onClick={(e) => e.stopPropagation()}
      >
        {/* 标题区 */}
        <div className="flex items-start justify-between mb-3">
          <div>
            <h3 className="text-base font-bold" style={{ color: 'var(--text-primary)' }}>
              {project.display_name || project.name}
            </h3>
            {project.description && (
              <p className="text-xs mt-1" style={{ color: 'var(--text-muted)' }}>{project.description}</p>
            )}
          </div>
          <button onClick={onClose} className="btn-ghost px-2 py-1 text-xs">✕</button>
        </div>

        {/* 元数据网格 */}
        <div className="grid grid-cols-2 sm:grid-cols-3 gap-2 mb-3 text-[11px]">
          <Field label="状态" value={LIFECYCLE_LABELS[project.lifecycle_stage]} color={accent} />
          <Field label="来源" value={project.source_type} />
          <Field label="类型" value={project.type} />
          <Field label="domain" value={project.domain || '-'} />
          <Field label="优先级" value={String(project.priority)} />
          <Field label="健康度" value={String(project.health_score)} />
          {project.repo_url && (
            <Field label="repo" value={
              <a href={project.repo_url} target="_blank" rel="noreferrer" className="hover:underline" style={{ color: 'var(--color-ai)' }}>
                {project.repo_url.replace('https://github.com/', '')}
              </a>
            } />
          )}
          {project.local_path && <Field label="local_path" value={project.local_path} />}
          {project.source_item_id && (
            <Field label="源资讯" value={
              <a href={`/api/knowledge/items/${project.source_item_id}`} target="_blank" rel="noreferrer" className="hover:underline" style={{ color: 'var(--color-ai)' }}>
                {project.source_item_id.slice(0, 8)}…
              </a>
            } />
          )}
        </div>

        {/* tags / tech_stack */}
        {(project.tags.length > 0 || project.tech_stack.length > 0) && (
          <div className="flex flex-wrap gap-1 mb-3">
            {project.tags.map(t => (
              <span key={t} className="text-[10px] px-1.5 py-0.5 rounded" style={{ backgroundColor: 'var(--bg-hover)', color: 'var(--text-secondary)' }}>#{t}</span>
            ))}
            {project.tech_stack.map(t => (
              <span key={t} className="text-[10px] px-1.5 py-0.5 rounded" style={{ backgroundColor: '#3b82f620', color: '#3b82f6' }}>{t}</span>
            ))}
          </div>
        )}

        {/* 上游状态 */}
        {project.source_type === 'fork' && project.upstream_url && (
          <UpstreamStatus
            project={project}
            onSync={handleSync}
          />
        )}

        {/* lifecycle 切换 */}
        <div className="mt-4 mb-3">
          <div className="text-[10px] mb-1.5" style={{ color: 'var(--text-muted)' }}>状态切换</div>
          <div className="flex flex-wrap gap-1">
            {ALL_STAGES.map(s => (
              <button
                key={s}
                onClick={() => handleTransition(s)}
                disabled={s === project.lifecycle_stage}
                className="text-[10px] px-2 py-0.5 rounded"
                style={{
                  backgroundColor: s === project.lifecycle_stage ? LIFECYCLE_COLORS[s] : 'var(--bg-hover)',
                  color: s === project.lifecycle_stage ? '#fff' : 'var(--text-secondary)',
                  cursor: s === project.lifecycle_stage ? 'default' : 'pointer',
                }}
              >
                {LIFECYCLE_LABELS[s]}
              </button>
            ))}
          </div>
        </div>

        {/* 阶段时间线 */}
        <div className="mt-4 mb-3">
          <div className="text-[10px] mb-1.5" style={{ color: 'var(--text-muted)' }}>阶段时间线</div>
          {loading ? (
            <div className="text-xs" style={{ color: 'var(--text-muted)' }}>加载中…</div>
          ) : stages.length === 0 ? (
            <div className="text-[10px]" style={{ color: 'var(--text-muted)' }}>暂无阶段记录</div>
          ) : (
            <div className="flex flex-col gap-1">
              {stages.map(st => (
                <div key={st.id} className="flex items-center gap-2 text-[10px]">
                  <span className="font-mono" style={{ color: 'var(--text-muted)' }}>#{st.stage_order}</span>
                  <span style={{ color: 'var(--text-primary)' }}>{st.stage_name}</span>
                  <span style={{ color: 'var(--text-secondary)' }}>[{st.status}]</span>
                  {st.started_at && (
                    <span style={{ color: 'var(--text-muted)' }}>{new Date(st.started_at).toLocaleString()}</span>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>

        {/* 活动日志 */}
        <div className="mt-4">
          <div className="text-[10px] mb-1.5" style={{ color: 'var(--text-muted)' }}>最近活动</div>
          {loading ? (
            <div className="text-xs" style={{ color: 'var(--text-muted)' }}>加载中…</div>
          ) : activities.length === 0 ? (
            <div className="text-[10px]" style={{ color: 'var(--text-muted)' }}>暂无活动</div>
          ) : (
            <div className="flex flex-col gap-1 max-h-40 overflow-y-auto">
              {activities.slice(0, 20).map(a => (
                <div key={a.id} className="flex items-start gap-2 text-[10px]">
                  <span style={{ color: 'var(--text-muted)' }}>{new Date(a.created_at).toLocaleString()}</span>
                  <span style={{ color: 'var(--text-secondary)' }}>{a.activity_type}</span>
                </div>
              ))}
            </div>
          )}
        </div>

        {toast && (
          <div
            className="fixed bottom-4 left-1/2 -translate-x-1/2 px-3 py-1.5 rounded-[var(--radius-sm)] text-xs"
            style={{
              backgroundColor: toast.kind === 'ok' ? '#00c96a' : '#e85d5d',
              color: '#fff',
            }}
          >
            {toast.msg}
          </div>
        )}
      </div>
    </div>
  );
}

function Field({ label, value, color }: { label: string; value: ReactNode; color?: string }) {
  return (
    <div>
      <div className="text-[9px]" style={{ color: 'var(--text-muted)' }}>{label}</div>
      <div className="text-[11px] font-mono" style={{ color: color || 'var(--text-primary)' }}>{value}</div>
    </div>
  );
}
