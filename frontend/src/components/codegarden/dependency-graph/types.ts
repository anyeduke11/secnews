/**
 * dependency-graph/types — DependencyGraph 共享类型 & 常量。
 *
 * Phase 1B: 拆自原 DependencyGraph.tsx, 集中放置颜色/标签/节点边 props。
 * 避免子组件之间循环 import, 状态/回调通过 props 注入。
 */
import type { CgDependency, DepEntityType, DepType } from '../../../types/codegarden';

export const DEP_TYPE_COLORS: Record<DepType, string> = {
  code: '#3b82f6',
  service: '#10b981',
  data: '#e8891a',
};

export const ENTITY_TYPE_COLORS: Record<DepEntityType, string> = {
  project: '#7c6aff',
  service: '#06b6d4',
};

export const DEP_TYPE_LABELS: Record<DepType, string> = {
  code: '代码',
  service: '服务',
  data: '数据',
};

/** 图谱内部使用的简化节点类型 */
export interface GraphNode {
  id: string;
  type: DepEntityType;
  label: string;
}

/** 图谱内部使用的简化边类型 */
export interface GraphEdge {
  id: string;
  source: string;
  target: string;
  dep_type: DepType;
  _depth?: number;
}

export interface DepGraphProps {
  nodes: GraphNode[];
  edges: GraphEdge[];
}

/** 节点在 SVG 中的位置 */
export interface NodePosition {
  x: number;
  y: number;
}

export interface DepListProps {
  dependencies: CgDependency[];
  onRemove: (id: string) => void | Promise<void>;
  onImpact: (targetType: DepEntityType, targetId: string) => void;
}

export interface ImpactResultDialogProps {
  result: CgDependency[];
  onClose: () => void;
}

export interface AddDependencyDialogProps {
  onClose: () => void;
  onAdd: (req: {
    source_type: DepEntityType;
    source_id: string;
    target_type: DepEntityType;
    target_id: string;
    dep_type: DepType;
  }) => Promise<void>;
}
