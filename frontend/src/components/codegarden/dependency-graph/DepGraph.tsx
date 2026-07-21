/**
 * DepGraph — 依赖图谱 SVG 渲染（节点 + 边 + 颜色图例）。
 *
 * Phase 1B: 拆自原 DependencyGraph.tsx SVG 段。
 * props-only: 接收 nodes + edges, 内部计算圆形布局 + 渲染。
 * 节点位置算法: 极坐标均布, 单节点时居中。
 */
import { useMemo } from 'react';
import { DepType } from '../../../types/codegarden';
import {
  DepGraphProps,
  NodePosition,
  DEP_TYPE_COLORS,
  DEP_TYPE_LABELS,
  ENTITY_TYPE_COLORS,
} from './types';

const SVG_W = 700;
const SVG_H = 400;

export function DepGraph({ nodes, edges }: DepGraphProps) {
  const positions = useMemo<NodePosition[]>(() => {
    const radius = Math.min(SVG_W, SVG_H) / 2 - 60;
    const cx = SVG_W / 2;
    const cy = SVG_H / 2;
    return nodes.map((_, i) => {
      if (nodes.length === 1) return { x: cx, y: cy };
      const angle = (2 * Math.PI * i) / nodes.length - Math.PI / 2;
      return {
        x: cx + radius * Math.cos(angle),
        y: cy + radius * Math.sin(angle),
      };
    });
  }, [nodes.length]);

  const nodePos = (id: string): NodePosition | null => {
    const idx = nodes.findIndex((n) => n.id === id);
    return idx >= 0 ? positions[idx] : null;
  };

  return (
    <>
      <div
        className="overflow-auto"
        style={{ backgroundColor: 'var(--bg-hover)', borderRadius: 'var(--radius-sm)' }}
      >
        <svg width={SVG_W} height={SVG_H} style={{ display: 'block' }}>
          <defs>
            {(Object.keys(DEP_TYPE_COLORS) as DepType[]).map((k) => (
              <marker
                key={k}
                id={`arrow-${k}`}
                viewBox="0 0 10 10"
                refX={8}
                refY={5}
                markerWidth={6}
                markerHeight={6}
                orient="auto-start-reverse"
              >
                <path d="M 0 0 L 10 5 L 0 10 z" fill={DEP_TYPE_COLORS[k]} />
              </marker>
            ))}
          </defs>

          {/* 边 */}
          {edges.map((edge) => {
            const src = nodePos(edge.source);
            const tgt = nodePos(edge.target);
            if (!src || !tgt) return null;
            const color = DEP_TYPE_COLORS[edge.dep_type];
            return (
              <g key={edge.id}>
                <line
                  x1={src.x}
                  y1={src.y}
                  x2={tgt.x}
                  y2={tgt.y}
                  stroke={color}
                  strokeWidth={1.5}
                  markerEnd={`url(#arrow-${edge.dep_type})`}
                  opacity={0.7}
                />
                <text
                  x={(src.x + tgt.x) / 2}
                  y={(src.y + tgt.y) / 2 - 4}
                  textAnchor="middle"
                  fontSize={8}
                  fill={color}
                >
                  {DEP_TYPE_LABELS[edge.dep_type]}
                  {edge._depth !== undefined ? ` (d=${edge._depth})` : ''}
                </text>
              </g>
            );
          })}

          {/* 节点 */}
          {nodes.map((node, i) => {
            const pos = positions[i];
            const color = ENTITY_TYPE_COLORS[node.type];
            return (
              <g key={node.id} transform={`translate(${pos.x},${pos.y})`}>
                <rect
                  x={-50}
                  y={-15}
                  width={100}
                  height={30}
                  rx={6}
                  fill="var(--bg-elevated)"
                  stroke={color}
                  strokeWidth={2}
                />
                <text
                  y={-2}
                  textAnchor="middle"
                  fontSize={9}
                  fill={color}
                  fontWeight="bold"
                >
                  {node.type}
                </text>
                <text
                  y={9}
                  textAnchor="middle"
                  fontSize={8}
                  fill="var(--text-primary)"
                >
                  {node.label.length > 14 ? node.label.slice(0, 13) + '…' : node.label}
                </text>
              </g>
            );
          })}
        </svg>
      </div>

      {/* 图例 */}
      <div className="flex items-center gap-3 mt-2 flex-wrap text-[10px]">
        <span style={{ color: 'var(--text-muted)' }}>依赖类型:</span>
        {(Object.keys(DEP_TYPE_COLORS) as DepType[]).map((k) => (
          <span key={k} className="flex items-center gap-1">
            <span
              style={{ display: 'inline-block', width: 12, height: 2, backgroundColor: DEP_TYPE_COLORS[k] }}
            />
            <span style={{ color: 'var(--text-secondary)' }}>{DEP_TYPE_LABELS[k]}</span>
          </span>
        ))}
        <span className="ml-3" style={{ color: 'var(--text-muted)' }}>实体:</span>
        {(Object.keys(ENTITY_TYPE_COLORS) as Array<keyof typeof ENTITY_TYPE_COLORS>).map((k) => (
          <span key={k} className="flex items-center gap-1">
            <span
              style={{ display: 'inline-block', width: 10, height: 10, backgroundColor: ENTITY_TYPE_COLORS[k] }}
            />
            <span style={{ color: 'var(--text-secondary)' }}>{k}</span>
          </span>
        ))}
      </div>
    </>
  );
}
