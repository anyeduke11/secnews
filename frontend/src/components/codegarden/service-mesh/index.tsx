/**
 * ServiceMesh — M2 服务网格主面板（Phase 1B 拆分后）。
 *
 * Phase 1B: 拆自原 ServiceMesh.tsx (16KB / 437 行 → 4 文件, 每文件 ≤ 10KB)。
 * 本文件仅做组合 + 状态管理 + 副作用（拉取/扫描/重启/日志/指标）。
 * 渲染委托给 ServiceCard / ServiceDetailDialog。
 *
 * 公开 API 完全保留（<ServiceMesh onShowTopology={...} />）。
 */
import { useState } from 'react';
import { CgService, ServiceRuntime, ServiceStatus, ServiceType } from '../../../types/codegarden';
import { useCodegardenServices } from '../../../hooks/useCodegardenServices';
import { Icon } from '../../Icon';
import { ServiceCard } from './ServiceCard';
import { ServiceDetailDialog } from './ServiceDetailDialog';
import {
  RUNTIME_OPTIONS,
  STATUS_OPTIONS,
  TYPE_OPTIONS,
  STATUS_LABELS,
  ServiceMeshProps,
  FlashKind,
} from './types';

export function ServiceMesh({ onShowTopology }: ServiceMeshProps) {
  const {
    items, total, loading, error,
    runtime, status, serviceType, keyword,
    setRuntime, setStatus, setServiceType, setKeyword,
    refresh, scan, restart, getLogs, getMetrics,
  } = useCodegardenServices();

  const [selected, setSelected] = useState<CgService | null>(null);
  const [toast, setToast] = useState<{ kind: FlashKind; msg: string } | null>(null);

  const flash = (kind: FlashKind, msg: string) => {
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
            style={{
              backgroundColor: 'var(--bg-hover)',
              color: 'var(--text-primary)',
              border: '1px solid var(--border-color)',
            }}
          >
            {RUNTIME_OPTIONS.map((r) => (
              <option key={r} value={r}>
                {r === 'all' ? '全部运行时' : r}
              </option>
            ))}
          </select>
          <select
            value={status}
            onChange={(e) => setStatus(e.target.value as ServiceStatus | 'all')}
            className="text-[11px] px-2 py-1 rounded"
            style={{
              backgroundColor: 'var(--bg-hover)',
              color: 'var(--text-primary)',
              border: '1px solid var(--border-color)',
            }}
          >
            {STATUS_OPTIONS.map((s) => (
              <option key={s} value={s}>
                {s === 'all' ? '全部状态' : STATUS_LABELS[s as ServiceStatus]}
              </option>
            ))}
          </select>
          <select
            value={serviceType}
            onChange={(e) => setServiceType(e.target.value as ServiceType | 'all')}
            className="text-[11px] px-2 py-1 rounded"
            style={{
              backgroundColor: 'var(--bg-hover)',
              color: 'var(--text-primary)',
              border: '1px solid var(--border-color)',
            }}
          >
            {TYPE_OPTIONS.map((t) => (
              <option key={t} value={t}>
                {t === 'all' ? '全部类型' : t}
              </option>
            ))}
          </select>
          <input
            value={keyword}
            onChange={(e) => setKeyword(e.target.value)}
            placeholder="搜索 name / namespace"
            className="text-[11px] px-2 py-1 rounded min-w-[180px]"
            style={{
              backgroundColor: 'var(--bg-hover)',
              color: 'var(--text-primary)',
              border: '1px solid var(--border-color)',
            }}
          />
        </div>
        <div className="flex items-center gap-2">
          <span className="text-xs" style={{ color: 'var(--text-muted)' }}>
            共 {total}
          </span>
          {onShowTopology && (
            <button
              onClick={onShowTopology}
              className="btn-ghost px-2.5 py-1.5 text-xs"
              title="查看拓扑图"
            >
              <Icon>
                <circle cx="12" cy="12" r="3" />
                <path d="M3 12h6M15 12h6" />
              </Icon>
            </button>
          )}
          <button
            onClick={handleScan}
            className="btn-ghost px-2.5 py-1.5 text-xs"
            title="扫描本地服务"
          >
            <Icon>
              <circle cx="11" cy="11" r="8" />
              <line x1="21" y1="21" x2="16.65" y2="16.65" />
            </Icon>
          </button>
          <button
            onClick={refresh}
            className="btn-ghost px-2 py-1.5 text-xs"
            title="刷新"
          >
            <Icon>
              <polyline points="23 4 23 10 17 10" />
              <path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15" />
            </Icon>
          </button>
        </div>
      </div>

      {loading ? (
        <div
          className="text-xs text-center py-6"
          style={{ color: 'var(--text-muted)' }}
        >
          加载中…
        </div>
      ) : error ? (
        <div className="text-xs text-center py-6" style={{ color: '#e85d5d' }}>
          {error}
        </div>
      ) : items.length === 0 ? (
        <div
          className="text-xs text-center py-6"
          style={{ color: 'var(--text-muted)' }}
        >
          暂无服务，点击右上角放大镜扫描本地
        </div>
      ) : (
        <div
          className="grid gap-2"
          style={{ gridTemplateColumns: 'repeat(auto-fill, minmax(260px, 1fr))' }}
        >
          {items.map((s) => (
            <ServiceCard key={s.id} service={s} onClick={() => setSelected(s)} />
          ))}
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
