// frontend/src/components/codegarden/ServiceMesh.tsx
// M2 服务网格主面板 — 服务列表 + 详情弹窗（含日志/指标/重启）
import { useEffect, useState } from 'react';
import {
  CgService,
  ServiceRuntime,
  ServiceStatus,
  ServiceType,
  SERVICE_RUNTIME_COLORS,
  SERVICE_STATUS_COLORS,
} from '../../types/codegarden';
import { useCodegardenServices } from '../../hooks/useCodegardenServices';
import { Icon } from '../Icon';

const RUNTIME_OPTIONS: Array<ServiceRuntime | 'all'> = ['all', 'docker', 'pm2', 'system', 'bare'];
const STATUS_OPTIONS: Array<ServiceStatus | 'all'> = ['all', 'running', 'stopped', 'error', 'unknown'];
const TYPE_OPTIONS: Array<ServiceType | 'all'> = ['all', 'http', 'websocket', 'grpc', 'static', 'database'];

const STATUS_LABELS: Record<ServiceStatus, string> = {
  running: '运行中', stopped: '已停止', error: '异常', unknown: '未知',
};

interface ServiceMeshProps {
  onShowTopology?: () => void;
}

export function ServiceMesh({ onShowTopology }: ServiceMeshProps) {
  const {
    items, total, loading, error,
    runtime, status, serviceType, keyword,
    setRuntime, setStatus, setServiceType, setKeyword,
    refresh, scan, restart, getLogs, getMetrics,
  } = useCodegardenServices();

  const [selected, setSelected] = useState<CgService | null>(null);
  const [toast, setToast] = useState<{ kind: 'ok' | 'err'; msg: string } | null>(null);

  const flash = (kind: 'ok' | 'err', msg: string) => {
    setToast({ kind, msg });
    setTimeout(() => setToast(null), 3000);
  };

  const handleScan = async () => {
    try {
      const r = await scan();
      flash('ok', `扫描完成: 新增 ${r.created} / 更新 ${r.updated} / 共 ${r.scanned}`);
    } catch (e: any) {
      flash('err', e?.message || String(e));
    }
  };

  return (
    <div>
      <div className="flex items-center justify-between mb-3 flex-wrap gap-2">
        <div className="flex items-center gap-2 flex-wrap">
          <select
            value={runtime}
            onChange={(e) => setRuntime(e.target.value as ServiceRuntime | 'all')}
            className="text-[11px] px-2 py-1 rounded"
            style={{ backgroundColor: 'var(--bg-hover)', color: 'var(--text-primary)', border: '1px solid var(--border-color)' }}
          >
            {RUNTIME_OPTIONS.map(r => <option key={r} value={r}>{r === 'all' ? '全部运行时' : r}</option>)}
          </select>
          <select
            value={status}
            onChange={(e) => setStatus(e.target.value as ServiceStatus | 'all')}
            className="text-[11px] px-2 py-1 rounded"
            style={{ backgroundColor: 'var(--bg-hover)', color: 'var(--text-primary)', border: '1px solid var(--border-color)' }}
          >
            {STATUS_OPTIONS.map(s => <option key={s} value={s}>{s === 'all' ? '全部状态' : STATUS_LABELS[s as ServiceStatus]}</option>)}
          </select>
          <select
            value={serviceType}
            onChange={(e) => setServiceType(e.target.value as ServiceType | 'all')}
            className="text-[11px] px-2 py-1 rounded"
            style={{ backgroundColor: 'var(--bg-hover)', color: 'var(--text-primary)', border: '1px solid var(--border-color)' }}
          >
            {TYPE_OPTIONS.map(t => <option key={t} value={t}>{t === 'all' ? '全部类型' : t}</option>)}
          </select>
          <input
            value={keyword}
            onChange={(e) => setKeyword(e.target.value)}
            placeholder="搜索 name / namespace"
            className="text-[11px] px-2 py-1 rounded min-w-[180px]"
            style={{ backgroundColor: 'var(--bg-hover)', color: 'var(--text-primary)', border: '1px solid var(--border-color)' }}
          />
        </div>
        <div className="flex items-center gap-2">
          <span className="text-xs" style={{ color: 'var(--text-muted)' }}>共 {total}</span>
          {onShowTopology && (
            <button onClick={onShowTopology} className="btn-ghost px-2.5 py-1.5 text-xs" title="查看拓扑图">
              <Icon><circle cx="12" cy="12" r="3" /><path d="M3 12h6M15 12h6" /></Icon>
            </button>
          )}
          <button onClick={handleScan} className="btn-ghost px-2.5 py-1.5 text-xs" title="扫描本地服务">
            <Icon><circle cx="11" cy="11" r="8" /><line x1="21" y1="21" x2="16.65" y2="16.65" /></Icon>
          </button>
          <button onClick={refresh} className="btn-ghost px-2 py-1.5 text-xs" title="刷新">
            <Icon><polyline points="23 4 23 10 17 10" /><path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15" /></Icon>
          </button>
        </div>
      </div>

      {loading ? (
        <div className="text-xs text-center py-6" style={{ color: 'var(--text-muted)' }}>加载中…</div>
      ) : error ? (
        <div className="text-xs text-center py-6" style={{ color: '#e85d5d' }}>{error}</div>
      ) : items.length === 0 ? (
        <div className="text-xs text-center py-6" style={{ color: 'var(--text-muted)' }}>
          暂无服务，点击右上角放大镜扫描本地
        </div>
      ) : (
        <div className="grid gap-2" style={{ gridTemplateColumns: 'repeat(auto-fill, minmax(260px, 1fr))' }}>
          {items.map(s => <ServiceCard key={s.id} service={s} onClick={() => setSelected(s)} />)}
        </div>
      )}

      {selected && (
        <ServiceDetailDialog
          service={selected}
          onClose={() => setSelected(null)}
          onRestart={restart}
          getLogs={getLogs}
          getMetrics={getMetrics}
          onFlash={flash}
        />
      )}

      {toast && (
        <div
          className="fixed bottom-4 left-1/2 -translate-x-1/2 px-3 py-1.5 rounded text-xs z-50"
          style={{
            backgroundColor: toast.kind === 'ok' ? '#00c96a' : '#e85d5d',
            color: '#fff',
          }}
        >
          {toast.msg}
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// ServiceCard
// ---------------------------------------------------------------------------
interface ServiceCardProps {
  service: CgService;
  onClick?: () => void;
}

function ServiceCard({ service, onClick }: ServiceCardProps) {
  const runtimeColor = SERVICE_RUNTIME_COLORS[service.runtime];
  const statusColor = SERVICE_STATUS_COLORS[service.status];
  return (
    <div
      onClick={onClick}
      className="rounded-[var(--radius-sm)] p-2.5 cursor-pointer transition-colors"
      style={{
        backgroundColor: 'var(--bg-elevated)',
        border: '1px solid var(--border-color)',
        borderLeft: `3px solid ${statusColor}`,
      }}
    >
      <div className="flex items-start justify-between gap-2">
        <div className="flex-1 min-w-0">
          <div className="text-xs font-semibold truncate" style={{ color: 'var(--text-primary)' }} title={service.name}>
            {service.name}
          </div>
          {service.namespace && (
            <div className="text-[10px] mt-0.5" style={{ color: 'var(--text-muted)' }}>
              {service.namespace}
            </div>
          )}
        </div>
        <span
          className="shrink-0 text-[9px] px-1.5 py-0.5 rounded"
          style={{ backgroundColor: statusColor + '20', color: statusColor }}
        >
          {STATUS_LABELS[service.status]}
        </span>
      </div>

      <div className="flex items-center gap-1.5 mt-2 flex-wrap">
        <span
          className="text-[9px] px-1.5 py-0.5 rounded"
          style={{ backgroundColor: runtimeColor + '20', color: runtimeColor }}
        >
          {service.runtime}
        </span>
        <span className="text-[9px] px-1.5 py-0.5 rounded" style={{ backgroundColor: 'var(--bg-hover)', color: 'var(--text-secondary)' }}>
          {service.type}
        </span>
        {service.endpoint_port && (
          <span className="text-[9px] font-mono px-1.5 py-0.5 rounded" style={{ backgroundColor: 'var(--bg-hover)', color: 'var(--text-secondary)' }}>
            :{service.endpoint_port}
          </span>
        )}
        {service.endpoint_domain && (
          <span className="text-[9px] truncate max-w-[100px]" style={{ color: 'var(--text-muted)' }} title={service.endpoint_domain}>
            {service.endpoint_domain}
          </span>
        )}
      </div>

      {service.dependencies && service.dependencies.length > 0 && (
        <div className="text-[9px] mt-1.5" style={{ color: 'var(--text-muted)' }}>
          ↳ 依赖 {service.dependencies.length} 项
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// ServiceDetailDialog
// ---------------------------------------------------------------------------
interface ServiceDetailDialogProps {
  service: CgService;
  onClose: () => void;
  onRestart: (id: string) => Promise<{ task_id: number }>;
  getLogs: (id: string, tail?: number) => Promise<string>;
  getMetrics: (id: string) => Promise<Record<string, unknown>>;
  onFlash: (kind: 'ok' | 'err', msg: string) => void;
}

function ServiceDetailDialog({ service, onClose, onRestart, getLogs, getMetrics, onFlash }: ServiceDetailDialogProps) {
  const [tab, setTab] = useState<'meta' | 'logs' | 'metrics'>('meta');
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
            <h3 className="text-sm font-bold" style={{ color: 'var(--text-primary)' }}>{service.name}</h3>
            {service.namespace && (
              <p className="text-[11px]" style={{ color: 'var(--text-muted)' }}>{service.namespace}</p>
            )}
          </div>
          <div className="flex items-center gap-2">
            <button onClick={handleRestart} className="btn-ghost px-2.5 py-1 text-[11px]" title="重启服务">
              ↻ 重启
            </button>
            <button onClick={onClose} className="btn-ghost px-2 py-1 text-[11px]">✕</button>
          </div>
        </div>

        <div className="flex items-center gap-2 mb-3">
          <span className="text-[10px] px-1.5 py-0.5 rounded" style={{ backgroundColor: runtimeColor + '20', color: runtimeColor }}>
            {service.runtime}
          </span>
          <span className="text-[10px] px-1.5 py-0.5 rounded" style={{ backgroundColor: statusColor + '20', color: statusColor }}>
            {STATUS_LABELS[service.status]}
          </span>
          <span className="text-[10px] px-1.5 py-0.5 rounded" style={{ backgroundColor: 'var(--bg-hover)', color: 'var(--text-secondary)' }}>
            {service.type}
          </span>
          {service.endpoint_port && (
            <span className="text-[10px] font-mono px-1.5 py-0.5 rounded" style={{ backgroundColor: 'var(--bg-hover)', color: 'var(--text-secondary)' }}>
              :{service.endpoint_port}
            </span>
          )}
        </div>

        <div className="flex items-center gap-1 mb-2 border-b" style={{ borderColor: 'var(--border-color)' }}>
          {(['meta', 'logs', 'metrics'] as const).map(t => (
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
                <div className="text-[10px] mb-1" style={{ color: 'var(--text-muted)' }}>依赖项 ({service.dependencies.length})</div>
                <div className="flex flex-wrap gap-1">
                  {service.dependencies.map((d, i) => (
                    <span key={i} className="text-[10px] px-1.5 py-0.5 rounded font-mono" style={{ backgroundColor: 'var(--bg-hover)', color: 'var(--text-secondary)' }}>
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
              <div className="text-[11px] text-center py-3" style={{ color: 'var(--text-muted)' }}>加载日志中…</div>
            ) : logs ? (
              <pre
                className="text-[10px] font-mono p-2 rounded max-h-96 overflow-auto"
                style={{ backgroundColor: 'var(--bg-hover)', color: 'var(--text-secondary)', whiteSpace: 'pre-wrap' }}
              >
                {logs}
              </pre>
            ) : (
              <div className="text-[11px] text-center py-3" style={{ color: 'var(--text-muted)' }}>无日志</div>
            )}
          </div>
        )}

        {tab === 'metrics' && (
          <div>
            {loadingTab ? (
              <div className="text-[11px] text-center py-3" style={{ color: 'var(--text-muted)' }}>加载指标中…</div>
            ) : metrics ? (
              <pre
                className="text-[10px] font-mono p-2 rounded max-h-96 overflow-auto"
                style={{ backgroundColor: 'var(--bg-hover)', color: 'var(--text-secondary)', whiteSpace: 'pre-wrap' }}
              >
                {JSON.stringify(metrics, null, 2)}
              </pre>
            ) : (
              <div className="text-[11px] text-center py-3" style={{ color: 'var(--text-muted)' }}>无指标</div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

function MetaRow({ label, value, mono }: { label: string; value: string; mono?: boolean }) {
  return (
    <div>
      <div className="text-[10px]" style={{ color: 'var(--text-muted)' }}>{label}</div>
      <div
        className={mono ? 'font-mono' : ''}
        style={{ color: 'var(--text-primary)', wordBreak: 'break-all' }}
      >
        {value}
      </div>
    </div>
  );
}
