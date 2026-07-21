/**
 * DependencyGraph — M4 依赖图谱主面板（Phase 1B 拆分后）。
 *
 * Phase 1B: 拆自原 DependencyGraph.tsx (16KB / 420 行 → 5 文件, 每文件 ≤ 10KB)。
 * 子组件:
 *   - DepGraph           节点/边 SVG 渲染
 *   - DepList            卡片列表 + 删除 + 影响分析入口
 *   - AddDependencyDialog 添加弹窗
 *   - ImpactResultDialog 影响分析结果弹窗
 *
 * 公开 API 完全保留（<DependencyGraph />）。
 */
import { useMemo, useState } from 'react';
import { CgDependency, DepEntityType } from '../../../types/codegarden';
import { useCodegardenOrchestration } from '../../../hooks/useCodegardenOrchestration';
import { Icon } from '../../Icon';
import { DepGraph } from './DepGraph';
import { DepList } from './DepList';
import { AddDependencyDialog } from './AddDependencyDialog';
import { ImpactResultDialog } from './ImpactResultDialog';
import { GraphNode, GraphEdge } from './types';

export function DependencyGraph() {
  const {
    dependencies,
    loadingDeps,
    error,
    addDependency,
    removeDependency,
    refreshDeps,
    impactAnalysis,
  } = useCodegardenOrchestration();
  const [impactResult, setImpactResult] = useState<CgDependency[] | null>(null);
  const [impactLoading, setImpactLoading] = useState(false);
  const [showAddDialog, setShowAddDialog] = useState(false);

  // 派生图节点 / 边
  const { nodes, edges } = useMemo(() => {
    const nodeMap = new Map<string, GraphNode>();
    for (const d of dependencies) {
      const sk = `${d.source_type}:${d.source_id}`;
      const tk = `${d.target_type}:${d.target_id}`;
      if (!nodeMap.has(sk)) {
        nodeMap.set(sk, { id: sk, type: d.source_type, label: d.source_id });
      }
      if (!nodeMap.has(tk)) {
        nodeMap.set(tk, { id: tk, type: d.target_type, label: d.target_id });
      }
    }
    const nodeList = Array.from(nodeMap.values());
    const edgeList: GraphEdge[] = dependencies.map((d, i) => ({
      id: `e${i}`,
      source: `${d.source_type}:${d.source_id}`,
      target: `${d.target_type}:${d.target_id}`,
      dep_type: d.dep_type,
      _depth: d._depth,
    }));
    return { nodes: nodeList, edges: edgeList };
  }, [dependencies]);

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

  return (
    <div>
      <div className="flex items-center justify-between mb-3 flex-wrap gap-2">
        <h3 className="text-sm font-bold" style={{ color: 'var(--text-primary)' }}>
          依赖图谱{' '}
          <span
            className="text-[10px] font-normal"
            style={{ color: 'var(--text-muted)' }}
          >
            ({dependencies.length})
          </span>
        </h3>
        <div className="flex items-center gap-2">
          <button
            onClick={() => setShowAddDialog(true)}
            className="btn-ghost px-2.5 py-1.5 text-xs"
            style={{ color: 'var(--color-ai)' }}
          >
            + 添加依赖
          </button>
          <button
            onClick={refreshDeps}
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

      {loadingDeps ? (
        <div className="text-xs text-center py-6" style={{ color: 'var(--text-muted)' }}>
          加载中…
        </div>
      ) : error ? (
        <div className="text-xs text-center py-6" style={{ color: 'var(--color-error)' }}>
          {error}
        </div>
      ) : dependencies.length === 0 ? (
        <div className="text-xs text-center py-6" style={{ color: 'var(--text-muted)' }}>
          暂无依赖关系，点击右上角添加
        </div>
      ) : (
        <>
          <DepGraph nodes={nodes} edges={edges} />
          <DepList
            dependencies={dependencies}
            onRemove={removeDependency}
            onImpact={handleImpact}
          />
        </>
      )}

      {impactLoading && (
        <div className="text-xs text-center py-2" style={{ color: 'var(--text-muted)' }}>
          分析中…
        </div>
      )}
      {impactResult && (
        <ImpactResultDialog
          result={impactResult}
          onClose={() => setImpactResult(null)}
        />
      )}

      {showAddDialog && (
        <AddDependencyDialog
          onClose={() => setShowAddDialog(false)}
          onAdd={async (req) => {
            await addDependency(req);
            setShowAddDialog(false);
          }}
        />
      )}
    </div>
  );
}
