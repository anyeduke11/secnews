/**
 * PortPool — 端口池视图（8000-9999 网格，每格 20 端口）。
 *
 * Phase 1B: 拆自原 ResourceHub.tsx PortPool 段。
 * props-only: 接收 items + onAllocate + onRelease, 内部管 toast / selectedPort / 自定义端口输入。
 * 状态: free / allocated / reserved / protected (8898)
 */
import { useMemo, useState } from 'react';
import { CgResource } from '../../../types/codegarden';
import {
  PortPoolProps,
  FlashKind,
  PortStatus,
  PORT_STATUS_COLORS,
  PORT_RANGE_END,
  PORT_RANGE_START,
  PROTECTED_COLOR,
  PROTECTED_PORTS,
} from './types';

const BLOCK_SIZE = 20;

export function PortPool({ items, onAllocate, onRelease }: PortPoolProps) {
  const [toast, setToast] = useState<{ kind: FlashKind; msg: string } | null>(null);
  const [customPort, setCustomPort] = useState('');
  const [selectedPort, setSelectedPort] = useState<number | null>(null);

  const flash = (kind: FlashKind, msg: string) => {
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
    for (let start = PORT_RANGE_START; start <= PORT_RANGE_END; start += BLOCK_SIZE) {
      arr.push({ start, end: Math.min(start + BLOCK_SIZE - 1, PORT_RANGE_END) });
    }
    return arr;
  }, []);

  const getPortStatus = (port: number): PortStatus => {
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

  const colorOf = (status: PortStatus): string => {
    if (status === 'protected') return PROTECTED_COLOR;
    return PORT_STATUS_COLORS[status];
  };

  return (
    <div>
      <div className="flex items-center gap-2 mb-3 flex-wrap">
        <input
          value={customPort}
          onChange={(e) => setCustomPort(e.target.value)}
          placeholder={`${PORT_RANGE_START}-${PORT_RANGE_END}`}
          className="text-[11px] px-2 py-1 rounded font-mono w-32"
          style={{
            backgroundColor: 'var(--bg-hover)',
            color: 'var(--text-primary)',
            border: '1px solid var(--border-color)',
          }}
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
          {(['free', 'allocated', 'reserved'] as const).map((k) => (
            <span key={k} className="flex items-center gap-1">
              <span
                style={{ display: 'inline-block', width: 10, height: 10, backgroundColor: PORT_STATUS_COLORS[k] }}
              />
              <span style={{ color: 'var(--text-muted)' }}>
                {k === 'free' ? '空闲' : k === 'allocated' ? '已分配' : '预留'}
              </span>
            </span>
          ))}
          <span className="flex items-center gap-1">
            <span
              style={{ display: 'inline-block', width: 10, height: 10, backgroundColor: PROTECTED_COLOR }}
            />
            <span style={{ color: 'var(--text-muted)' }}>保护(8898)</span>
          </span>
        </div>
      </div>

      <div
        className="grid gap-1 p-2 rounded"
        style={{
          backgroundColor: 'var(--bg-hover)',
          gridTemplateColumns: 'repeat(auto-fill, minmax(180px, 1fr))',
        }}
      >
        {blocks.map((block) => {
          const ports = [];
          for (let p = block.start; p <= block.end; p++) {
            ports.push({ port: p, status: getPortStatus(p) });
          }
          const allocated = ports.filter((p) => p.status === 'allocated').length;
          const free = ports.filter((p) => p.status === 'free').length;
          return (
            <div
              key={block.start}
              className="rounded p-1.5"
              style={{
                backgroundColor: 'var(--bg-elevated)',
                border: '1px solid var(--border-color)',
              }}
            >
              <div className="flex items-center justify-between text-[9px] mb-1">
                <span className="font-mono" style={{ color: 'var(--text-muted)' }}>
                  {block.start}-{block.end}
                </span>
                <span style={{ color: 'var(--text-muted)' }}>
                  {free}/{ports.length}
                </span>
              </div>
              <div
                className="grid gap-0.5"
                style={{ gridTemplateColumns: 'repeat(10, 1fr)' }}
              >
                {ports.map(({ port, status }) => (
                  <button
                    key={port}
                    onClick={() => setSelectedPort(port)}
                    title={`端口 ${port} (${status})`}
                    className="aspect-square rounded-sm"
                    style={{
                      backgroundColor: colorOf(status),
                      cursor: 'pointer',
                      border: selectedPort === port ? '2px solid var(--color-ai)' : 'none',
                    }}
                  />
                ))}
              </div>
              {allocated > 0 && (
                <div
                  className="text-[8px] mt-1 text-center"
                  style={{ color: 'var(--text-muted)' }}
                >
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
            style={{
              backgroundColor: 'var(--bg-elevated)',
              border: '1px solid var(--border-color)',
            }}
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-center justify-between mb-2">
              <span className="text-sm font-bold" style={{ color: 'var(--text-primary)' }}>
                端口 {selectedPort}
              </span>
              <button onClick={() => setSelectedPort(null)} className="btn-ghost px-2 py-1 text-[11px]">
                ✕
              </button>
            </div>
            <div className="text-[11px] mb-2" style={{ color: 'var(--text-secondary)' }}>
              状态: {getPortStatus(selectedPort)}
            </div>
            {getPortStatus(selectedPort) === 'free' && !PROTECTED_PORTS.has(selectedPort) && (
              <button
                onClick={() => {
                  handleAllocate(selectedPort);
                  setSelectedPort(null);
                }}
                className="btn-ghost w-full py-1.5 text-[11px]"
                style={{ color: 'var(--color-ai)' }}
              >
                分配此端口
              </button>
            )}
            {(getPortStatus(selectedPort) === 'allocated' ||
              getPortStatus(selectedPort) === 'reserved') && (
              <button
                onClick={() => handleRelease(selectedPort)}
                className="btn-ghost w-full py-1.5 text-[11px]"
                style={{ color: '#e85d5d' }}
              >
                释放此端口
              </button>
            )}
            {PROTECTED_PORTS.has(selectedPort) && (
              <div
                className="text-[11px] text-center py-2"
                style={{ color: '#e85d5d' }}
              >
                受保护端口，禁止分配/释放
              </div>
            )}
          </div>
        </div>
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
