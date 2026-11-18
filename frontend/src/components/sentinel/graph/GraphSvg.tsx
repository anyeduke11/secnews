/**
 * GraphSvg — 知识图谱主体: 零依赖手写 SVG (确定性域扇区布局, 无 physics 抖动) (B5 从 SentinelGraphPage 抽出)
 *
 * 无障碍: 整张图为 role="img" + aria-label 描述数量与分布 (文案由容器 buildSvgLabel 产出),
 * 三个图层全部 aria-hidden; 等价操作由「节点索引」文字列表提供 (GraphCanvas 内)。
 * 画布模式下的固定像素尺寸与 zoom 感知命中圆也在这里, 但 canvasMode 状态与 InfiniteCanvas 包装留在容器。
 */
import {
  domainFill, domainLabel, ellipsis, VIEW_H, VIEW_W,
  type GraphEdge, type GraphNode, type PlacedNode,
} from './graphModel';

export function GraphSvg({ rendered, visibleEdges, posOf, index, domain, selectedId, svgLabel, canvasMode, canvasHitZoom, onPick }: {
  rendered: PlacedNode[];
  visibleEdges: GraphEdge[];
  posOf: Map<string, PlacedNode>;
  index: PlacedNode[];
  domain: string;
  selectedId?: string;
  svgLabel: string;
  canvasMode: boolean;
  canvasHitZoom: number;
  onPick: (node: GraphNode) => void;
}) {
  const matchOf = (node: { dom: string }) => domain === 'all' || node.dom === domain;
  return (
    <svg
      className="kg-graphsvg"
      viewBox={`0 0 ${VIEW_W} ${VIEW_H}`}
      role="img"
      aria-label={svgLabel}
      style={canvasMode ? { width: VIEW_W, height: VIEW_H } : undefined}
    >
      <g className="kg-layer-edges" aria-hidden="true">
        {visibleEdges.map((e, i) => {
          const a = posOf.get(e.source)!;
          const b = posOf.get(e.target)!;
          const dim = !(matchOf(a) && matchOf(b));
          return (
            <line
              key={`${e.source}-${e.target}-${i}`}
              className={`kg-edge${e.weight >= 4 ? ' kg-edge-strong' : ''}${dim ? ' kg-dim' : ''}`}
              x1={a.x}
              y1={a.y}
              x2={b.x}
              y2={b.y}
            />
          );
        })}
      </g>
      <g className="kg-layer-nodes" aria-hidden="true">
        {rendered.map(n => {
          const dim = !matchOf(n);
          const isSel = selectedId === n.id;
          const fill = n.vuln ? 'kg-f-vuln' : domainFill(n.dom);
          const shape = n.vuln
            ? <polygon className={`kg-shape ${fill}`} points={`${n.x},${n.y - n.r - 1} ${n.x + n.r},${n.y + n.r * 0.8} ${n.x - n.r},${n.y + n.r * 0.8}`} />
            : n.r >= 11 || n.dom === 'unknown'
              ? <rect className={`kg-shape ${fill}`} x={n.x - n.r} y={n.y - n.r} width={n.r * 2} height={n.r * 2} rx={2} />
              : <circle className={`kg-shape ${fill}`} cx={n.x} cy={n.y} r={n.r} />;
          const showLab = isSel || (!dim && (n.vuln || n.deg >= 4 || n.count >= 3 || n.r >= 11));
          return (
            <g
              key={n.id}
              className={`kg-node${isSel ? ' is-sel' : ''}`}
              data-dim={dim ? '1' : '0'}
              onClick={() => onPick(n)}
            >
              <title>{`${n.id} · ${n.label}（${domainLabel(n.dom)} · 关联 ${n.deg} 条边 · ${n.count} 条来源条目）`}</title>
              {/* A4: 画布模式下放大透明命中圆 (fill=none 不参与绘制, 仅扩大点击热区);
                  r 随画布 zoom 反向补偿, 极小 zoom 下节点仍可点中 */}
              {canvasMode && (
                <circle
                  className="kg-hit"
                  cx={n.x}
                  cy={n.y}
                  r={Math.max(n.r, Math.min(48, 14 / canvasHitZoom))}
                  fill="none"
                  pointerEvents="all"
                />
              )}
              {isSel && (
                <>
                  <circle className="kg-sel-halo" cx={n.x} cy={n.y} r={n.r + 11} />
                  <circle className="kg-sel-ring" cx={n.x} cy={n.y} r={n.r + 6} />
                </>
              )}
              {shape}
              {showLab && (
                <text className={isSel ? 'kg-lab-code' : 'kg-lab'} x={n.x} y={n.y + n.r + 13} textAnchor="middle">
                  {ellipsis(n.label)}
                </text>
              )}
            </g>
          );
        })}
      </g>
      <g className="kg-layer-hubs" aria-hidden="true">
        {index.slice(0, 4).map(n => (
          <text key={`hub-${n.id}`} className="kg-lab num" x={n.x} y={n.y - n.r - 7} textAnchor="middle">
            {`deg ${n.deg}`}
          </text>
        ))}
      </g>
    </svg>
  );
}
