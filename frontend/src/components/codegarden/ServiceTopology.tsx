// frontend/src/components/codegarden/ServiceTopology.tsx
// M2 服务拓扑图 — 用 SVG 渲染 nodes + edges（不引入 React Flow，避免重依赖）
// Phase 4: SVG 颜色经 useThemeColors 解析, 暗/亮主题自动切换; 错误态用 --color-error
import { useEffect, useState } from 'react';
import { CgServiceTopology, ServiceRuntime, ServiceStatus } from '../../types/codegarden';
import { Icon } from '../Icon';
import { useThemeColors, ThemeColorKey } from '../../hooks/useThemeColors';
import { EmptyState } from '../EmptyState';

interface ServiceTopologyProps {
  fetchTopology: () => Promise<CgServiceTopology>;
  onClose?: () => void;
}

// 运行时 → token key 映射 (SVG stroke 需要字面色值)
const RUNTIME_TOKEN: Record<ServiceRuntime, ThemeColorKey> = {
  docker: 'color-info',
  pm2: 'color-ai',
  system: 'text-muted',
  bare: 'text-secondary',
};

// 状态 → token key 映射 (SVG fill 需要字面色值)
const STATUS_TOKEN: Record<ServiceStatus, ThemeColorKey> = {
  running: 'color-success',
  stopped: 'text-muted',
  error: 'color-error',
  unknown: 'color-warning',
};

// 圆形布局：把 nodes 均匀分布在圆周上
function computeLayout(nodeCount: number, radius: number, centerX: number, centerY: number) {
  const positions: Array<{ x: number; y: number }> = [];
  if (nodeCount === 0) return positions;
  if (nodeCount === 1) {
    positions.push({ x: centerX, y: centerY });
    return positions;
  }
  for (let i = 0; i < nodeCount; i++) {
    const angle = (2 * Math.PI * i) / nodeCount - Math.PI / 2;
    positions.push({
      x: centerX + radius * Math.cos(angle),
      y: centerY + radius * Math.sin(angle),
    });
  }
  return positions;
}

export function ServiceTopology({ fetchTopology, onClose }: ServiceTopologyProps) {
  const [topology, setTopology] = useState<CgServiceTopology | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = async () => {
    setLoading(true);
    setError(null);
    try {
      const t = await fetchTopology();
      setTopology(t);
    } catch (e: any) {
      setError(e?.message || String(e));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); /* eslint-disable-next-line */ }, []);

  const W = 800;
  const H = 500;
  const radius = Math.min(W, H) / 2 - 80;
  const positions = computeLayout(topology?.nodes?.length || 0, radius, W / 2, H / 2);
  const nodeById = new Map((topology?.nodes || []).map((n, i) => [n.id, { node: n, pos: positions[i] }]));

  // 读取 SVG 需要字面色的 token
  const colors = useThemeColors([
    'text-primary', 'text-secondary', 'text-muted', 'border-color',
    'bg-elevated',
    'color-info', 'color-ai', 'color-success', 'color-warning', 'color-error',
  ]);
  const runtimeColor = (r: ServiceRuntime) => colors[RUNTIME_TOKEN[r]] || 'var(--text-muted)';
  const statusColor = (s: ServiceStatus) => colors[STATUS_TOKEN[s]] || 'var(--text-muted)';
  const runtimeLabel: Record<ServiceRuntime, string> = {
    docker: 'docker', pm2: 'pm2', system: 'system', bare: 'bare',
  };
  const statusLabel: Record<ServiceStatus, string> = {
    running: 'running', stopped: 'stopped', error: 'error', unknown: 'unknown',
  };

  return (
    <div>
      <div className="flex items-center justify-between mb-3">
        <h3 className="text-sm font-bold" style={{ color: 'var(--text-primary)' }}>
          服务拓扑图
        </h3>
        <div className="flex items-center gap-2">
          <button onClick={load} className="btn-ghost px-2 py-1 text-[11px]" title="刷新">
            <Icon><polyline points="23 4 23 10 17 10" /><path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15" /></Icon>
          </button>
          {onClose && (
            <button onClick={onClose} className="btn-ghost px-2 py-1 text-[11px]">✕</button>
          )}
        </div>
      </div>

      {loading ? (
        <p className="text-xs text-center py-6" style={{ color: 'var(--text-muted)' }}>加载中…</p>
      ) : error ? (
        <div
          className="rounded-[var(--radius-md)] p-2.5 text-xs"
          style={{
            backgroundColor: 'color-mix(in srgb, var(--color-error) 12%, transparent)',
            border: '1px solid var(--color-error)',
            color: 'var(--color-error)',
          }}
        >
          加载失败: {error}
        </div>
      ) : !topology || topology.nodes.length === 0 ? (
        <EmptyState
          title="暂无服务"
          description="请先扫描本地服务"
        />
      ) : (
        <>
          <div className="overflow-auto" style={{ backgroundColor: 'var(--bg-hover)', borderRadius: 'var(--radius-sm)' }}>
            <svg width={W} height={H} style={{ display: 'block' }}>
              {/* edges */}
              {topology.edges.map(edge => {
                const src = nodeById.get(edge.source);
                const tgt = nodeById.get(edge.target);
                if (!src || !tgt) return null;
                const midX = (src.pos.x + tgt.pos.x) / 2;
                const midY = (src.pos.y + tgt.pos.y) / 2;
                return (
                  <g key={edge.id}>
                    <line
                      x1={src.pos.x}
                      y1={src.pos.y}
                      x2={tgt.pos.x}
                      y2={tgt.pos.y}
                      stroke={colors['border-color'] || 'var(--border-color)'}
                      strokeWidth={1.5}
                      markerEnd="url(#arrow)"
                    />
                    <text
                      x={midX}
                      y={midY - 4}
                      textAnchor="middle"
                      fontSize={9}
                      fill={colors['text-muted'] || 'var(--text-muted)'}
                    >
                      {edge.data?.dep_type || ''}
                    </text>
                  </g>
                );
              })}
              {/* nodes */}
              {topology.nodes.map((node, i) => {
                const pos = positions[i];
                const rColor = runtimeColor(node.data.runtime);
                const sColor = statusColor(node.data.status);
                return (
                  <g key={node.id} transform={`translate(${pos.x},${pos.y})`}>
                    <circle
                      r={28}
                      fill={colors['bg-elevated'] || 'var(--bg-elevated)'}
                      stroke={rColor}
                      strokeWidth={2.5}
                    />
                    <circle r={4} cx={20} cy={-20} fill={sColor} stroke={colors['bg-elevated'] || 'var(--bg-elevated)'} strokeWidth={1.5} />
                    <text
                      y={4}
                      textAnchor="middle"
                      fontSize={10}
                      fill={colors['text-primary'] || 'var(--text-primary)'}
                      fontWeight="bold"
                    >
                      {node.data.label.length > 10 ? node.data.label.slice(0, 9) + '…' : node.data.label}
                    </text>
                    <text
                      y={18}
                      textAnchor="middle"
                      fontSize={8}
                      fill={colors['text-muted'] || 'var(--text-muted)'}
                    >
                      {node.data.runtime}
                    </text>
                  </g>
                );
              })}
              <defs>
                <marker
                  id="arrow"
                  viewBox="0 0 10 10"
                  refX="8"
                  refY="5"
                  markerWidth="6"
                  markerHeight="6"
                  orient="auto-start-reverse"
                >
                  <path d="M 0 0 L 10 5 L 0 10 z" fill={colors['border-color'] || 'var(--border-color)'} />
                </marker>
              </defs>
            </svg>
          </div>
          <div className="flex items-center gap-3 mt-2 flex-wrap text-[10px]">
            <span style={{ color: 'var(--text-muted)' }}>运行时:</span>
            {(Object.keys(RUNTIME_TOKEN) as ServiceRuntime[]).map((k) => (
              <span key={k} className="flex items-center gap-1">
                <span style={{ display: 'inline-block', width: 8, height: 8, borderRadius: '50%', backgroundColor: runtimeColor(k) }} />
                <span style={{ color: 'var(--text-secondary)' }}>{runtimeLabel[k]}</span>
              </span>
            ))}
            <span className="ml-3" style={{ color: 'var(--text-muted)' }}>状态:</span>
            {(Object.keys(STATUS_TOKEN) as ServiceStatus[]).map((k) => (
              <span key={k} className="flex items-center gap-1">
                <span style={{ display: 'inline-block', width: 8, height: 8, borderRadius: '50%', backgroundColor: statusColor(k) }} />
                <span style={{ color: 'var(--text-secondary)' }}>{statusLabel[k]}</span>
              </span>
            ))}
          </div>
        </>
      )}
    </div>
  );
}
