// frontend/src/components/codegarden/DependencyGraph.tsx
// M4 依赖图谱 — SVG 节点（project+service）+ 三类依赖边（code/service/data）
import { useEffect, useMemo, useState } from 'react';
import {
  CgDependency,
  DepEntityType,
  DepType,
} from '../../types/codegarden';
import { useCodegardenOrchestration } from '../../hooks/useCodegardenOrchestration';
import { Icon } from '../Icon';

const DEP_TYPE_COLORS: Record<DepType, string> = {
  code: '#3b82f6',
  service: '#10b981',
  data: '#e8891a',
};

const ENTITY_TYPE_COLORS: Record<DepEntityType, string> = {
  project: '#7c6aff',
  service: '#06b6d4',
};

const DEP_TYPE_LABELS: Record<DepType, string> = {
  code: '代码',
  service: '服务',
  data: '数据',
};

export function DependencyGraph() {
  const { dependencies, loadingDeps, error, addDependency, removeDependency, refreshDeps, impactAnalysis } = useCodegardenOrchestration();
  const [impactResult, setImpactResult] = useState<CgDependency[] | null>(null);
  const [impactLoading, setImpactLoading] = useState(false);
  const [showAddDialog, setShowAddDialog] = useState(false);

  const { nodes, edges } = useMemo(() => {
    const nodeMap = new Map<string, { id: string; type: DepEntityType; label: string }>();
    for (const d of dependencies) {
      const sk = `${d.source_type}:${d.source_id}`;
      const tk = `${d.target_type}:${d.target_id}`;
      if (!nodeMap.has(sk)) nodeMap.set(sk, { id: sk, type: d.source_type, label: d.source_id });
      if (!nodeMap.has(tk)) nodeMap.set(tk, { id: tk, type: d.target_type, label: d.target_id });
    }
    const nodeList = Array.from(nodeMap.values());
    const edgeList = dependencies.map((d, i) => ({
      id: `e${i}`,
      source: `${d.source_type}:${d.source_id}`,
      target: `${d.target_type}:${d.target_id}`,
      dep_type: d.dep_type,
      _depth: d._depth,
    }));
    return { nodes: nodeList, edges: edgeList };
  }, [dependencies]);

  const positions = useMemo(() => {
    const W = 700, H = 400, radius = Math.min(W, H) / 2 - 60;
    const cx = W / 2, cy = H / 2;
    return nodes.map((_, i) => {
      if (nodes.length === 1) return { x: cx, y: cy };
      const angle = (2 * Math.PI * i) / nodes.length - Math.PI / 2;
      return { x: cx + radius * Math.cos(angle), y: cy + radius * Math.sin(angle) };
    });
  }, [nodes.length]);

  const handleImpact = async (targetType: DepEntityType, targetId: string) => {
    setImpactLoading(true);
    setImpactResult(null);
    try {
      const result = await impactAnalysis(targetType, targetId);
      setImpactResult(result);
    } catch (e: any) {
      window.alert(e?.message || String(e));
    } finally {
      setImpactLoading(false);
    }
  };

  const nodePos = (id: string) => {
    const idx = nodes.findIndex(n => n.id === id);
    return idx >= 0 ? positions[idx] : null;
  };

  return (
    <div>
      <div className="flex items-center justify-between mb-3 flex-wrap gap-2">
        <h3 className="text-sm font-bold" style={{ color: 'var(--text-primary)' }}>
          依赖图谱 <span className="text-[10px] font-normal" style={{ color: 'var(--text-muted)' }}>({dependencies.length})</span>
        </h3>
        <div className="flex items-center gap-2">
          <button
            onClick={() => setShowAddDialog(true)}
            className="btn-ghost px-2.5 py-1.5 text-xs"
            style={{ color: 'var(--color-ai)' }}
          >
            + 添加依赖
          </button>
          <button onClick={refreshDeps} className="btn-ghost px-2 py-1.5 text-xs" title="刷新">
            <Icon><polyline points="23 4 23 10 17 10" /><path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15" /></Icon>
          </button>
        </div>
      </div>

      {loadingDeps ? (
        <div className="text-xs text-center py-6" style={{ color: 'var(--text-muted)' }}>加载中…</div>
      ) : error ? (
        <div className="text-xs text-center py-6" style={{ color: '#e85d5d' }}>{error}</div>
      ) : dependencies.length === 0 ? (
        <div className="text-xs text-center py-6" style={{ color: 'var(--text-muted)' }}>
          暂无依赖关系，点击右上角添加
        </div>
      ) : (
        <>
          <div className="overflow-auto" style={{ backgroundColor: 'var(--bg-hover)', borderRadius: 'var(--radius-sm)' }}>
            <svg width={700} height={400} style={{ display: 'block' }}>
              <defs>
                {Object.entries(DEP_TYPE_COLORS).map(([k, c]) => (
                  <marker key={k} id={`arrow-${k}`} viewBox="0 0 10 10" refX="8" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
                    <path d="M 0 0 L 10 5 L 0 10 z" fill={c} />
                  </marker>
                ))}
              </defs>
              {edges.map(edge => {
                const src = nodePos(edge.source);
                const tgt = nodePos(edge.target);
                if (!src || !tgt) return null;
                const color = DEP_TYPE_COLORS[edge.dep_type];
                return (
                  <g key={edge.id}>
                    <line x1={src.x} y1={src.y} x2={tgt.x} y2={tgt.y} stroke={color} strokeWidth={1.5} markerEnd={`url(#arrow-${edge.dep_type})`} opacity={0.7} />
                    <text x={(src.x + tgt.x) / 2} y={(src.y + tgt.y) / 2 - 4} textAnchor="middle" fontSize={8} fill={color}>
                      {DEP_TYPE_LABELS[edge.dep_type]}{edge._depth !== undefined ? ` (d=${edge._depth})` : ''}
                    </text>
                  </g>
                );
              })}
              {nodes.map((node, i) => {
                const pos = positions[i];
                const color = ENTITY_TYPE_COLORS[node.type];
                return (
                  <g key={node.id} transform={`translate(${pos.x},${pos.y})`}>
                    <rect x={-50} y={-15} width={100} height={30} rx={6} fill="var(--bg-elevated)" stroke={color} strokeWidth={2} />
                    <text y={-2} textAnchor="middle" fontSize={9} fill={color} fontWeight="bold">{node.type}</text>
                    <text y={9} textAnchor="middle" fontSize={8} fill="var(--text-primary)">
                      {node.label.length > 14 ? node.label.slice(0, 13) + '…' : node.label}
                    </text>
                  </g>
                );
              })}
            </svg>
          </div>

          <div className="flex items-center gap-3 mt-2 flex-wrap text-[10px]">
            <span style={{ color: 'var(--text-muted)' }}>依赖类型:</span>
            {Object.entries(DEP_TYPE_COLORS).map(([k, c]) => (
              <span key={k} className="flex items-center gap-1">
                <span style={{ display: 'inline-block', width: 12, height: 2, backgroundColor: c }} />
                <span style={{ color: 'var(--text-secondary)' }}>{DEP_TYPE_LABELS[k as DepType]}</span>
              </span>
            ))}
            <span className="ml-3" style={{ color: 'var(--text-muted)' }}>实体:</span>
            {Object.entries(ENTITY_TYPE_COLORS).map(([k, c]) => (
              <span key={k} className="flex items-center gap-1">
                <span style={{ display: 'inline-block', width: 10, height: 10, backgroundColor: c }} />
                <span style={{ color: 'var(--text-secondary)' }}>{k}</span>
              </span>
            ))}
          </div>

          <div className="mt-3">
            <div className="text-[11px] mb-1.5" style={{ color: 'var(--text-muted)' }}>所有依赖</div>
            <div className="grid gap-1.5" style={{ gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))' }}>
              {dependencies.map(d => (
                <div key={d.id} className="rounded p-2 text-[10px]" style={{ backgroundColor: 'var(--bg-elevated)', border: '1px solid var(--border-color)' }}>
                  <div className="flex items-center justify-between mb-1">
                    <span style={{ color: DEP_TYPE_COLORS[d.dep_type] }}>{DEP_TYPE_LABELS[d.dep_type]}</span>
                    <button onClick={() => removeDependency(d.id).catch(e => window.alert(e?.message || e))} className="text-[9px]" style={{ color: '#e85d5d' }}>删除</button>
                  </div>
                  <div className="font-mono" style={{ color: 'var(--text-primary)' }}>{d.source_type}:{d.source_id}</div>
                  <div style={{ color: 'var(--text-muted)' }}>↓</div>
                  <div className="font-mono" style={{ color: 'var(--text-primary)' }}>{d.target_type}:{d.target_id}</div>
                  <button
                    onClick={() => handleImpact(d.target_type, d.target_id)}
                    className="mt-1.5 text-[9px] w-full py-0.5 rounded"
                    style={{ border: '1px solid var(--border-color)', color: 'var(--color-ai)' }}
                  >
                    影响分析
                  </button>
                </div>
              ))}
            </div>
          </div>
        </>
      )}

      {impactLoading && (
        <div className="text-xs text-center py-2" style={{ color: 'var(--text-muted)' }}>分析中…</div>
      )}
      {impactResult && (
        <div className="fixed inset-0 z-50 flex items-end sm:items-center justify-center p-4" style={{ backgroundColor: 'rgba(0,0,0,0.5)' }} onClick={() => setImpactResult(null)}>
          <div className="w-full max-w-md max-h-[80vh] overflow-y-auto rounded-[var(--radius-md)] p-3" style={{ backgroundColor: 'var(--bg-elevated)', border: '1px solid var(--border-color)' }} onClick={(e) => e.stopPropagation()}>
            <div className="flex items-center justify-between mb-2">
              <span className="text-sm font-bold" style={{ color: 'var(--text-primary)' }}>影响分析结果 ({impactResult.length})</span>
              <button onClick={() => setImpactResult(null)} className="btn-ghost px-2 py-1 text-[11px]">✕</button>
            </div>
            {impactResult.length === 0 ? (
              <div className="text-[11px] text-center py-3" style={{ color: 'var(--text-muted)' }}>无上游依赖</div>
            ) : (
              <div className="space-y-1.5">
                {impactResult.map(d => (
                  <div key={d.id} className="rounded p-2 text-[10px]" style={{ backgroundColor: 'var(--bg-hover)', border: '1px solid var(--border-color)' }}>
                    <div className="flex items-center justify-between mb-1">
                      <span style={{ color: DEP_TYPE_COLORS[d.dep_type] }}>{DEP_TYPE_LABELS[d.dep_type]}</span>
                      {d._depth !== undefined && <span className="font-mono" style={{ color: 'var(--text-muted)' }}>depth={d._depth}</span>}
                    </div>
                    <div className="font-mono" style={{ color: 'var(--text-primary)' }}>{d.source_type}:{d.source_id} → {d.target_type}:{d.target_id}</div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      )}

      {showAddDialog && (
        <AddDependencyDialog
          onClose={() => setShowAddDialog(false)}
          onAdd={async (req) => { await addDependency(req); setShowAddDialog(false); }}
        />
      )}
    </div>
  );
}

interface AddDependencyDialogProps {
  onClose: () => void;
  onAdd: (req: {
    source_type: DepEntityType;
    source_id: string;
    target_type: DepEntityType;
    target_id: string;
    dep_type: DepType;
  }) => Promise<void>;
}

function AddDependencyDialog({ onClose, onAdd }: AddDependencyDialogProps) {
  const [sourceType, setSourceType] = useState<DepEntityType>('project');
  const [sourceId, setSourceId] = useState('');
  const [targetType, setTargetType] = useState<DepEntityType>('service');
  const [targetId, setTargetId] = useState('');
  const [depType, setDepType] = useState<DepType>('code');
  const [err, setErr] = useState<string | null>(null);

  const submit = async () => {
    if (!sourceId.trim() || !targetId.trim()) { setErr('source_id 和 target_id 必填'); return; }
    try {
      await onAdd({
        source_type: sourceType, source_id: sourceId.trim(),
        target_type: targetType, target_id: targetId.trim(),
        dep_type: depType,
      });
    } catch (e: any) { setErr(e?.message || String(e)); }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4" style={{ backgroundColor: 'rgba(0,0,0,0.5)' }} onClick={onClose}>
      <div className="w-full max-w-md rounded-[var(--radius-md)] p-3" style={{ backgroundColor: 'var(--bg-elevated)', border: '1px solid var(--border-color)' }} onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-between mb-3">
          <span className="text-sm font-bold" style={{ color: 'var(--text-primary)' }}>添加依赖关系</span>
          <button onClick={onClose} className="btn-ghost px-2 py-1 text-[11px]">✕</button>
        </div>
        <div className="space-y-2 text-[11px]">
          <div className="grid grid-cols-2 gap-2">
            <div>
              <label className="text-[10px]" style={{ color: 'var(--text-muted)' }}>Source 类型</label>
              <select value={sourceType} onChange={(e) => setSourceType(e.target.value as DepEntityType)}
                className="w-full text-[11px] px-2 py-1 rounded"
                style={{ backgroundColor: 'var(--bg-hover)', color: 'var(--text-primary)', border: '1px solid var(--border-color)' }}>
                <option value="project">project</option>
                <option value="service">service</option>
              </select>
            </div>
            <div>
              <label className="text-[10px]" style={{ color: 'var(--text-muted)' }}>Source ID</label>
              <input value={sourceId} onChange={(e) => setSourceId(e.target.value)}
                className="w-full text-[11px] px-2 py-1 rounded font-mono"
                style={{ backgroundColor: 'var(--bg-hover)', color: 'var(--text-primary)', border: '1px solid var(--border-color)' }} />
            </div>
          </div>
          <div className="grid grid-cols-2 gap-2">
            <div>
              <label className="text-[10px]" style={{ color: 'var(--text-muted)' }}>Target 类型</label>
              <select value={targetType} onChange={(e) => setTargetType(e.target.value as DepEntityType)}
                className="w-full text-[11px] px-2 py-1 rounded"
                style={{ backgroundColor: 'var(--bg-hover)', color: 'var(--text-primary)', border: '1px solid var(--border-color)' }}>
                <option value="project">project</option>
                <option value="service">service</option>
              </select>
            </div>
            <div>
              <label className="text-[10px]" style={{ color: 'var(--text-muted)' }}>Target ID</label>
              <input value={targetId} onChange={(e) => setTargetId(e.target.value)}
                className="w-full text-[11px] px-2 py-1 rounded font-mono"
                style={{ backgroundColor: 'var(--bg-hover)', color: 'var(--text-primary)', border: '1px solid var(--border-color)' }} />
            </div>
          </div>
          <div>
            <label className="text-[10px]" style={{ color: 'var(--text-muted)' }}>依赖类型</label>
            <select value={depType} onChange={(e) => setDepType(e.target.value as DepType)}
              className="w-full text-[11px] px-2 py-1 rounded"
              style={{ backgroundColor: 'var(--bg-hover)', color: 'var(--text-primary)', border: '1px solid var(--border-color)' }}>
              <option value="code">code (代码)</option>
              <option value="service">service (服务)</option>
              <option value="data">data (数据)</option>
            </select>
          </div>
          {err && <div className="text-[10px]" style={{ color: '#e85d5d' }}>{err}</div>}
          <button onClick={submit} className="btn-ghost w-full py-1.5 text-[11px]" style={{ color: 'var(--color-ai)' }}>添加</button>
        </div>
      </div>
    </div>
  );
}
