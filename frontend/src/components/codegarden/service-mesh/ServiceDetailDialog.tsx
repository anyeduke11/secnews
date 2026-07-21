/**
 * ServiceDetailDialog — 服务详情弹窗（元数据/日志/指标 三 Tab + 重启）。
 *
 * Phase 1B: 拆自原 ServiceMesh.tsx ServiceDetailDialog + MetaRow。
 * Tab 切换懒加载, 元数据 Tab 即时渲染, 日志/指标按需 fetch。
 */
import { useEffect, useState } from 'react';
import { SERVICE_RUNTIME_COLORS, SERVICE_STATUS_COLORS } from '../../../types/codegarden';
import {
  ServiceDetailDialogProps,
  MetaRowProps,
  STATUS_LABELS,
} from './types';

type TabKey = 'meta' | 'logs' | 'metrics';

export function ServiceDetailDialog({
  service, onClose, onRestart, getLogs, getMetrics, onFlash,
}: ServiceDetailDialogProps) {
  const [tab, setTab] = useState<TabKey>('meta');
  const [logs, setLogs] = useState('');
  const [metrics, setMetrics] = useState<Record<string, unknown> | null>(null);
  const [loadingTab, setLoadingTab] = useState(false);

  const loadLogs = async () => {
    setLoadingTab(true);
    try {
      const txt = await getLogs(service.id, 200);
      setLogs(txt);
    } catch (e: any) {
      onFlash('err', e?.message || String(e));
    } finally {
      setLoadingTab(false);
    }
  };

  const loadMetrics = async () => {
    setLoadingTab(true);
    try {
      const m = await getMetrics(service.id);
      setMetrics(m);
    } catch (e: any) {
      onFlash('err', e?.message || String(e));
    } finally {
      setLoadingTab(false);
    }
  };

  useEffect(() => {
    if (tab === 'logs' && !logs) loadLogs();
    if (tab === 'metrics' && !metrics) loadMetrics();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tab]);

  const handleRestart = async () => {
    try {
      const { task_id } = await onRestart(service.id);
      onFlash('ok', `已触发重启 (task #${task_id})`);
    } catch (e: any) {
      onFlash('err', e?.message || String(e));
    }
  };

  const runtimeColor = SERVICE_RUNTIME_COLORS[service.runtime];
  const statusColor = SERVICE_STATUS_COLORS[service.status];

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
        <div className="flex items-start justify-between mb-3">
          <div>
            <h3 className="text-sm font-bold" style={{ color: 'var(--text-primary)' }}>
              {service.name}
            </h3>
            {service.namespace && (
              <p className="text-[11px]" style={{ color: 'var(--text-muted)' }}>
                {service.namespace}
              </p>
            )}
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={handleRestart}
              className="btn-ghost px-2.5 py-1 text-[11px]"
              title="重启服务"
            >
              ↻ 重启
            </button>
            <button onClick={onClose} className="btn-ghost px-2 py-1 text-[11px]">
              ✕
            </button>
          </div>
        </div>

        <div className="flex items-center gap-2 mb-3">
          <span
            className="text-[10px] px-1.5 py-0.5 rounded"
            style={{ backgroundColor: runtimeColor + '20', color: runtimeColor }}
          >
            {service.runtime}
          </span>
          <span
            className="text-[10px] px-1.5 py-0.5 rounded"
            style={{ backgroundColor: statusColor + '20', color: statusColor }}
          >
            {STATUS_LABELS[service.status]}
          </span>
          <span
            className="text-[10px] px-1.5 py-0.5 rounded"
            style={{ backgroundColor: 'var(--bg-hover)', color: 'var(--text-secondary)' }}
          >
            {service.type}
          </span>
          {service.endpoint_port && (
            <span
              className="text-[10px] font-mono px-1.5 py-0.5 rounded"
              style={{ backgroundColor: 'var(--bg-hover)', color: 'var(--text-secondary)' }}
            >
              :{service.endpoint_port}
            </span>
          )}
        </div>

        <div
          className="flex items-center gap-1 mb-2 border-b"
          style={{ borderColor: 'var(--border-color)' }}
        >
          {(['meta', 'logs', 'metrics'] as const).map((t) => (
            <button
              key={t}
              onClick={() => setTab(t)}
              className="px-3 py-1.5 text-[11px]"
              style={{
                color: tab === t ? 'var(--color-ai)' : 'var(--text-secondary)',
                borderBottom: tab === t ? '2px solid var(--color-ai)' : '2px solid transparent',
              }}
            >
              {t === 'meta' ? '元数据' : t === 'logs' ? '日志' : '指标'}
            </button>
          ))}
        </div>

        {tab === 'meta' && (
          <div className="grid grid-cols-2 gap-2 text-[11px]">
            <MetaRow label="ID" value={service.id} mono />
            <MetaRow label="项目 ID" value={service.project_id || '-'} mono />
            <MetaRow label="Host" value={service.endpoint_host || '-'} />
            <MetaRow label="Domain" value={service.endpoint_domain || '-'} />
            <MetaRow label="健康检查" value={service.health_check_type || '-'} />
            <MetaRow label="检查路径" value={service.health_check_path || '-'} />
            <MetaRow label="CPU 限制" value={service.cpu_limit || '-'} />
            <MetaRow label="内存限制" value={service.memory_limit || '-'} />
            <MetaRow label="创建时间" value={service.created_at?.slice(0, 19) || '-'} />
            <MetaRow label="最后检查" value={service.last_checked_at?.slice(0, 19) || '-'} />
            {service.dependencies.length > 0 && (
              <div className="col-span-2">
                <div className="text-[10px] mb-1" style={{ color: 'var(--text-muted)' }}>
                  依赖项 ({service.dependencies.length})
                </div>
                <div className="flex flex-wrap gap-1">
                  {service.dependencies.map((d, i) => (
                    <span
                      key={i}
                      className="text-[10px] px-1.5 py-0.5 rounded font-mono"
                      style={{ backgroundColor: 'var(--bg-hover)', color: 'var(--text-secondary)' }}
                    >
                      {d}
                    </span>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}

        {tab === 'logs' && (
          <div>
            {loadingTab ? (
              <div
                className="text-[11px] text-center py-3"
                style={{ color: 'var(--text-muted)' }}
              >
                加载日志中…
              </div>
            ) : logs ? (
              <pre
                className="text-[10px] font-mono p-2 rounded max-h-96 overflow-auto"
                style={{
                  backgroundColor: 'var(--bg-hover)',
                  color: 'var(--text-secondary)',
                  whiteSpace: 'pre-wrap',
                }}
              >
                {logs}
              </pre>
            ) : (
              <div
                className="text-[11px] text-center py-3"
                style={{ color: 'var(--text-muted)' }}
              >
                无日志
              </div>
            )}
          </div>
        )}

        {tab === 'metrics' && (
          <div>
            {loadingTab ? (
              <div
                className="text-[11px] text-center py-3"
                style={{ color: 'var(--text-muted)' }}
              >
                加载指标中…
              </div>
            ) : metrics ? (
              <pre
                className="text-[10px] font-mono p-2 rounded max-h-96 overflow-auto"
                style={{
                  backgroundColor: 'var(--bg-hover)',
                  color: 'var(--text-secondary)',
                  whiteSpace: 'pre-wrap',
                }}
              >
                {JSON.stringify(metrics, null, 2)}
              </pre>
            ) : (
              <div
                className="text-[11px] text-center py-3"
                style={{ color: 'var(--text-muted)' }}
              >
                无指标
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

function MetaRow({ label, value, mono }: MetaRowProps) {
  return (
    <div>
      <div className="text-[10px]" style={{ color: 'var(--text-muted)' }}>
        {label}
      </div>
      <div
        className={mono ? 'font-mono' : ''}
        style={{ color: 'var(--text-primary)', wordBreak: 'break-all' }}
      >
        {value}
      </div>
    </div>
  );
}
