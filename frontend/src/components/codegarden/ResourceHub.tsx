// frontend/src/components/codegarden/ResourceHub.tsx
// M3 资源中枢 — 4 tab（端口/域名/环境模板/卷）+ PortPool 网格 + allocate/release
import { useMemo, useState } from 'react';
import {
  CgResource,
  ResourceType,
  ResourceStatus,
  RESOURCE_TYPE_LABELS,
} from '../../types/codegarden';
import { useCodegardenResources } from '../../hooks/useCodegardenResources';
import { Icon } from '../Icon';

const PROTECTED_PORTS = new Set([8898]);
const PORT_RANGE_START = 8000;
const PORT_RANGE_END = 9999;
const PORT_STATUS_COLORS: Record<ResourceStatus, string> = {
  allocated: '#e85d5d',
  free: '#10b981',
  reserved: '#f0c929',
};

type Tab = ResourceType;

export function ResourceHub() {
  const [tab, setTab] = useState<Tab>('port');
  const {
    items, total, loading, error,
    resourceType, resourceStatus,
    setResourceType, setResourceStatus,
    refresh, allocatePort, releasePort, remove,
  } = useCodegardenResources();

  // 切换 tab 时同步筛选
  const switchTab = (t: Tab) => {
    setTab(t);
    setResourceType(t);
    setResourceStatus('all');
  };

  return (
    <div>
      <div className="flex items-center justify-between mb-3 flex-wrap gap-2">
        <div className="flex items-center gap-1 border-b" style={{ borderColor: 'var(--border-color)' }}>
          {(Object.keys(RESOURCE_TYPE_LABELS) as Tab[]).map(t => (
            <button
              key={t}
              onClick={() => switchTab(t)}
              className="px-3 py-1.5 text-[11px]"
              style={{
                color: tab === t ? 'var(--color-ai)' : 'var(--text-secondary)',
                borderBottom: tab === t ? '2px solid var(--color-ai)' : '2px solid transparent',
              }}
            >
              {RESOURCE_TYPE_LABELS[t]}
            </button>
          ))}
        </div>
        <div className="flex items-center gap-2">
          <span className="text-xs" style={{ color: 'var(--text-muted)' }}>共 {total}</span>
          <button onClick={refresh} className="btn-ghost px-2 py-1.5 text-xs" title="刷新">
            <Icon><polyline points="23 4 23 10 17 10" /><path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15" /></Icon>
          </button>
        </div>
      </div>

      {tab === 'port' && (
        <PortPool
          items={items.filter(it => it.type === 'port')}
          onAllocate={allocatePort}
          onRelease={releasePort}
        />
      )}

      {tab !== 'port' && (
        <>
          {loading ? (
            <div className="text-xs text-center py-6" style={{ color: 'var(--text-muted)' }}>加载中…</div>
          ) : error ? (
            <div className="text-xs text-center py-6" style={{ color: '#e85d5d' }}>{error}</div>
          ) : items.filter(it => it.type === tab).length === 0 ? (
            <div className="text-xs text-center py-6" style={{ color: 'var(--text-muted)' }}>
              暂无{RESOURCE_TYPE_LABELS[tab]}
            </div>
          ) : (
            <div className="grid gap-2" style={{ gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))' }}>
              {items.filter(it => it.type === tab).map(r => (
                <ResourceCard key={r.id} resource={r} onRemove={() => remove(r.id).catch(e => window.alert(e?.message || e))} />
              ))}
            </div>
          )}
        </>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// PortPool — 端口池视图（8000-9999 网格，每格 100 端口）
// ---------------------------------------------------------------------------
interface PortPoolProps {
  items: CgResource[];
  onAllocate: (req: { preferred_port?: number }) => Promise<CgResource>;
  onRelease: (port: number) => Promise<void>;
}

function PortPool({ items, onAllocate, onRelease }: PortPoolProps) {
  const [toast, setToast] = useState<{ kind: 'ok' | 'err'; msg: string } | null>(null);
  const [customPort, setCustomPort] = useState('');
  const [selectedPort, setSelectedPort] = useState<number | null>(null);

  const flash = (kind: 'ok' | 'err', msg: string) => {
    setToast({ kind, msg });
    setTimeout(() => setToast(null), 3000);
  };

  // 端口状态映射
  const portStatusMap = useMemo(() => {
    const m = new Map<number, CgResource>();
    for (const r of items) {
      if (r.type === 'port' && r.value) {
        const p = parseInt(r.value, 10);
        if (!isNaN(p)) m.set(p, r);
      }
    }
    return m;
  }, [items]);

  // 100 个块，每块 20 个端口
  const blocks = useMemo(() => {
    const arr: Array<{ start: number; end: number }> = [];
    for (let start = PORT_RANGE_START; start <= PORT_RANGE_END; start += 20) {
      arr.push({ start, end: Math.min(start + 19, PORT_RANGE_END) });
    }
    return arr;
  }, []);

  const getPortStatus = (port: number): 'free' | 'allocated' | 'reserved' | 'protected' => {
    if (PROTECTED_PORTS.has(port)) return 'protected';
    const r = portStatusMap.get(port);
    if (!r) return 'free';
    return r.status;
  };

  const handleAllocate = async (port?: number) => {
    try {
      const req = port ? { preferred_port: port } : {};
      const r = await onAllocate(req);
      flash('ok', `已分配端口 ${r.value}`);
    } catch (e: any) {
      flash('err', e?.message || String(e));
    }
  };

  const handleRelease = async (port: number) => {
    if (!window.confirm(`确认释放端口 ${port}？`)) return;
    try {
      await onRelease(port);
      flash('ok', `已释放端口 ${port}`);
      setSelectedPort(null);
    } catch (e: any) {
      flash('err', e?.message || String(e));
    }
  };

  const handleCustomAllocate = () => {
    const p = parseInt(customPort, 10);
    if (isNaN(p) || p < PORT_RANGE_START || p > PORT_RANGE_END) {
      flash('err', `端口必须在 ${PORT_RANGE_START}-${PORT_RANGE_END}`);
      return;
    }
    handleAllocate(p);
    setCustomPort('');
  };

  return (
    <div>
      <div className="flex items-center gap-2 mb-3 flex-wrap">
        <input
          value={customPort}
          onChange={(e) => setCustomPort(e.target.value)}
          placeholder={`${PORT_RANGE_START}-${PORT_RANGE_END}`}
          className="text-[11px] px-2 py-1 rounded font-mono w-32"
          style={{ backgroundColor: 'var(--bg-hover)', color: 'var(--text-primary)', border: '1px solid var(--border-color)' }}
        />
        <button
          onClick={handleCustomAllocate}
          className="btn-ghost px-2.5 py-1 text-[11px]"
          style={{ color: 'var(--color-ai)' }}
        >
          分配指定端口
        </button>
        <button
          onClick={() => handleAllocate()}
          className="btn-ghost px-2.5 py-1 text-[11px]"
          style={{ color: 'var(--color-ai)' }}
        >
          自动分配
        </button>
        <div className="flex items-center gap-2 ml-auto text-[10px]">
          <span className="flex items-center gap-1">
            <span style={{ display: 'inline-block', width: 10, height: 10, backgroundColor: PORT_STATUS_COLORS.free }} />
            <span style={{ color: 'var(--text-muted)' }}>空闲</span>
          </span>
          <span className="flex items-center gap-1">
            <span style={{ display: 'inline-block', width: 10, height: 10, backgroundColor: PORT_STATUS_COLORS.allocated }} />
            <span style={{ color: 'var(--text-muted)' }}>已分配</span>
          </span>
          <span className="flex items-center gap-1">
            <span style={{ display: 'inline-block', width: 10, height: 10, backgroundColor: PORT_STATUS_COLORS.reserved }} />
            <span style={{ color: 'var(--text-muted)' }}>预留</span>
          </span>
          <span className="flex items-center gap-1">
            <span style={{ display: 'inline-block', width: 10, height: 10, backgroundColor: '#3b82f6' }} />
            <span style={{ color: 'var(--text-muted)' }}>保护(8898)</span>
          </span>
        </div>
      </div>

      <div
        className="grid gap-1 p-2 rounded"
        style={{ backgroundColor: 'var(--bg-hover)', gridTemplateColumns: 'repeat(auto-fill, minmax(180px, 1fr))' }}
      >
        {blocks.map(block => {
          // 块的状态汇总
          const ports: Array<{ port: number; status: string }> = [];
          for (let p = block.start; p <= block.end; p++) {
            ports.push({ port: p, status: getPortStatus(p) });
          }
          const allocated = ports.filter(p => p.status === 'allocated').length;
          const free = ports.filter(p => p.status === 'free').length;
          return (
            <div
              key={block.start}
              className="rounded p-1.5"
              style={{ backgroundColor: 'var(--bg-elevated)', border: '1px solid var(--border-color)' }}
            >
              <div className="flex items-center justify-between text-[9px] mb-1">
                <span className="font-mono" style={{ color: 'var(--text-muted)' }}>{block.start}-{block.end}</span>
                <span style={{ color: 'var(--text-muted)' }}>{free}/{ports.length}</span>
              </div>
              <div className="grid gap-0.5" style={{ gridTemplateColumns: 'repeat(10, 1fr)' }}>
                {ports.map(({ port, status }) => (
                  <button
                    key={port}
                    onClick={() => setSelectedPort(port)}
                    title={`端口 ${port} (${status})`}
                    className="aspect-square rounded-sm"
                    style={{
                      backgroundColor:
                        status === 'protected' ? '#3b82f6' :
                        status === 'allocated' ? PORT_STATUS_COLORS.allocated :
                        status === 'reserved' ? PORT_STATUS_COLORS.reserved :
                        PORT_STATUS_COLORS.free,
                      cursor: 'pointer',
                      border: selectedPort === port ? '2px solid var(--color-ai)' : 'none',
                    }}
                  />
                ))}
              </div>
              {allocated > 0 && (
                <div className="text-[8px] mt-1 text-center" style={{ color: 'var(--text-muted)' }}>
                  已分配 {allocated}
                </div>
              )}
            </div>
          );
        })}
      </div>

      {selectedPort !== null && (
        <div
          className="fixed inset-0 z-50 flex items-end sm:items-center justify-center p-4"
          style={{ backgroundColor: 'rgba(0,0,0,0.5)' }}
          onClick={() => setSelectedPort(null)}
        >
          <div
            className="w-full max-w-sm rounded-[var(--radius-md)] p-3"
            style={{ backgroundColor: 'var(--bg-elevated)', border: '1px solid var(--border-color)' }}
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-center justify-between mb-2">
              <span className="text-sm font-bold" style={{ color: 'var(--text-primary)' }}>端口 {selectedPort}</span>
              <button onClick={() => setSelectedPort(null)} className="btn-ghost px-2 py-1 text-[11px]">✕</button>
            </div>
            <div className="text-[11px] mb-2" style={{ color: 'var(--text-secondary)' }}>
              状态: {getPortStatus(selectedPort)}
            </div>
            {getPortStatus(selectedPort) === 'free' && !PROTECTED_PORTS.has(selectedPort) && (
              <button
                onClick={() => { handleAllocate(selectedPort); setSelectedPort(null); }}
                className="btn-ghost w-full py-1.5 text-[11px]"
                style={{ color: 'var(--color-ai)' }}
              >
                分配此端口
              </button>
            )}
            {(getPortStatus(selectedPort) === 'allocated' || getPortStatus(selectedPort) === 'reserved') && (
              <button
                onClick={() => handleRelease(selectedPort)}
                className="btn-ghost w-full py-1.5 text-[11px]"
                style={{ color: '#e85d5d' }}
              >
                释放此端口
              </button>
            )}
            {PROTECTED_PORTS.has(selectedPort) && (
              <div className="text-[11px] text-center py-2" style={{ color: '#e85d5d' }}>
                受保护端口，禁止分配/释放
              </div>
            )}
          </div>
        </div>
      )}

      {toast && (
        <div
          className="fixed bottom-4 left-1/2 -translate-x-1/2 px-3 py-1.5 rounded text-xs z-50"
          style={{ backgroundColor: toast.kind === 'ok' ? '#00c96a' : '#e85d5d', color: '#fff' }}
        >
          {toast.msg}
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// ResourceCard — 通用资源卡片（domain/env_template/volume）
// ---------------------------------------------------------------------------
interface ResourceCardProps {
  resource: CgResource;
  onRemove?: () => void;
}

function ResourceCard({ resource, onRemove }: ResourceCardProps) {
  const statusColor =
    resource.status === 'allocated' ? '#e85d5d' :
    resource.status === 'reserved' ? '#f0c929' :
    '#10b981';

  return (
    <div
      className="rounded-[var(--radius-sm)] p-2.5"
      style={{
        backgroundColor: 'var(--bg-elevated)',
        border: '1px solid var(--border-color)',
        borderLeft: `3px solid ${statusColor}`,
      }}
    >
      <div className="flex items-start justify-between gap-2">
        <div className="flex-1 min-w-0">
          <div className="text-xs font-semibold truncate font-mono" style={{ color: 'var(--text-primary)' }} title={resource.value}>
            {resource.value}
          </div>
          <div className="text-[10px] mt-0.5" style={{ color: 'var(--text-muted)' }}>
            {RESOURCE_TYPE_LABELS[resource.type]}
          </div>
        </div>
        <span className="shrink-0 text-[9px] px-1.5 py-0.5 rounded" style={{ backgroundColor: statusColor + '20', color: statusColor }}>
          {resource.status}
        </span>
      </div>
      {resource.owner_service_id && (
        <div className="text-[10px] mt-1.5" style={{ color: 'var(--text-muted)' }}>
          ↳ service: <span className="font-mono">{resource.owner_service_id}</span>
        </div>
      )}
      {resource.owner_project_id && (
        <div className="text-[10px]" style={{ color: 'var(--text-muted)' }}>
          ↳ project: <span className="font-mono">{resource.owner_project_id}</span>
        </div>
      )}
      {resource.reserved_until && (
        <div className="text-[10px]" style={{ color: 'var(--text-muted)' }}>
          预留至: {resource.reserved_until.slice(0, 19)}
        </div>
      )}
      {onRemove && (
        <button
          onClick={onRemove}
          className="mt-2 text-[9px] w-full py-0.5 rounded"
          style={{ border: '1px solid var(--border-color)', color: '#e85d5d' }}
        >
          删除
        </button>
      )}
    </div>
  );
}
