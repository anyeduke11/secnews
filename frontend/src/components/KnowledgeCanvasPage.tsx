/**
 * 无限画布 /knowledge/canvas — NAV4 P3 占位视图 (DEV-0178 建, DEV-0184 升级)
 *
 * Phase 5 (DEV-0184): 双模式 —
 *  - 画布模式 (默认): 方案B 无限画布 paradigm, DOM 节点 + SVG 边,
 *    pan/zoom/节点拖拽/双击重置全交互, 复用共享 InfiniteCanvas
 *  - 印厂 demo (降级): 原 ECharts force-free 演示 (roam=true + draggable=true) 保留
 * 数据: 两者共用同一套 DEMO_NODES/DEMO_EDGES mock (纯前端, 无 API)。
 * 与 /knowledge/graph 区别: 该页是确定性扇区布局的知识图谱, 本页是 free-form 演示。
 */

import ReactECharts from 'echarts-for-react';
import { useMemo, useRef, useState } from 'react';
import { useI18n } from '../contexts/I18nContext';
import { InfiniteCanvas, useCanvasCoords } from './shared/editorial/InfiniteCanvas';

interface DemoNode {
  id: string;
  name: string;
  symbolSize: number;
  category: number;
  x?: number;
  y?: number;
}

interface DemoEdge {
  source: string;
  target: string;
}

const DEMO_NODES: DemoNode[] = [
  { id: 'collect', name: '采集', symbolSize: 60, category: 0, x: 100, y: 100 },
  { id: 'parse', name: '解析', symbolSize: 50, category: 1, x: 280, y: 80 },
  { id: 'judge', name: '研判', symbolSize: 70, category: 2, x: 460, y: 160 },
  { id: 'review', name: '复盘', symbolSize: 55, category: 2, x: 640, y: 100 },
  { id: 'action', name: '执行', symbolSize: 65, category: 3, x: 820, y: 200 },
  { id: 'feedback', name: '反馈', symbolSize: 45, category: 3, x: 700, y: 320 },
  { id: 'archive', name: '归档', symbolSize: 50, category: 4, x: 460, y: 360 },
  { id: 'replay', name: '回放', symbolSize: 40, category: 4, x: 220, y: 320 },
];

const DEMO_EDGES: DemoEdge[] = [
  { source: 'collect', target: 'parse' },
  { source: 'parse', target: 'judge' },
  { source: 'judge', target: 'review' },
  { source: 'review', target: 'action' },
  { source: 'action', target: 'feedback' },
  { source: 'feedback', target: 'archive' },
  { source: 'archive', target: 'replay' },
  { source: 'replay', target: 'collect' },
  { source: 'judge', target: 'action' },
  { source: 'review', target: 'archive' },
];

const DEMO_CATEGORIES = [
  { name: '入口' },
  { name: '处理' },
  { name: '判断' },
  { name: '行动' },
  { name: '沉淀' },
];

/** 画布模式节点色 (分类 → 全局分类 token, 随主题翻转) */
const CATEGORY_COLORS = [
  'var(--color-ai)',
  'var(--color-tech)',
  'var(--color-finance)',
  'var(--color-security)',
  'var(--color-startup)',
];

type PositionMap = Record<string, { x: number; y: number }>;

/** 画布模式: 可拖拽 DOM 节点 + SVG 边 (世界坐标, 随视口缩放平移);
 *  positions 状态由页面级持有 (A6: 边层/world 尺寸随节点位置动态扩张) */
function CanvasModeGraph({ positions, setPositions, width, height }: {
  positions: PositionMap;
  setPositions: React.Dispatch<React.SetStateAction<PositionMap>>;
  width: number;
  height: number;
}) {
  const coords = useCanvasCoords();
  const dragRef = useRef<{ id: string; gx: number; gy: number } | null>(null);

  function onNodePointerDown(e: React.PointerEvent, id: string) {
    const w = coords.toWorld(e.clientX, e.clientY);
    dragRef.current = { id, gx: w.x - positions[id].x, gy: w.y - positions[id].y };
    try {
      (e.currentTarget as HTMLElement).setPointerCapture(e.pointerId);
    } catch {
      // jsdom 无 setPointerCapture — 忽略
    }
    e.stopPropagation();
  }

  function onNodePointerMove(e: React.PointerEvent) {
    const d = dragRef.current;
    if (!d) return;
    const w = coords.toWorld(e.clientX, e.clientY);
    setPositions(cur => ({ ...cur, [d.id]: { x: w.x - d.gx, y: w.y - d.gy } }));
  }

  function onNodePointerUp() {
    dragRef.current = null;
  }

  const edgeLines = DEMO_EDGES.map((e, i) => {
    const a = positions[e.source];
    const b = positions[e.target];
    if (!a || !b) return null;
    return <line key={i} x1={a.x} y1={a.y} x2={b.x} y2={b.y} stroke="var(--line-strong)" strokeWidth={1.5} />;
  });

  return (
    <>
      <svg
        className="ic-edgesvg"
        data-testid="canvas-edgesvg"
        width={width}
        height={height}
        style={{ position: 'absolute', left: 0, top: 0, pointerEvents: 'none' }}
        aria-hidden="true"
      >
        {edgeLines}
      </svg>
      {DEMO_NODES.map(n => {
        const p = positions[n.id];
        return (
          <div
            key={n.id}
            data-canvas-node={n.id}
            data-testid={`canvas-node-${n.id}`}
            style={{
              left: p.x,
              top: p.y,
              transform: 'translate(-50%, -50%)',
              display: 'inline-flex',
              alignItems: 'center',
              gap: 7,
              padding: '7px 13px',
              borderRadius: 'var(--radius-md)',
              background: 'var(--bg-card)',
              border: `1.5px solid ${CATEGORY_COLORS[n.category] ?? 'var(--line-strong)'}`,
              color: 'var(--ink)',
              fontFamily: 'var(--font-sans)',
              fontSize: 13,
              fontWeight: 600,
              whiteSpace: 'nowrap',
              boxShadow: 'var(--shadow-pop)',
            }}
            title={`${n.name} · ${DEMO_CATEGORIES[n.category]?.name ?? ''} — 拖拽移动`}
            onPointerDown={e => onNodePointerDown(e, n.id)}
            onPointerMove={onNodePointerMove}
            onPointerUp={onNodePointerUp}
          >
            <i aria-hidden="true" style={{ width: 7, height: 7, borderRadius: 2, background: CATEGORY_COLORS[n.category] ?? 'var(--ink-3)', flexShrink: 0 }} />
            {n.name}
          </div>
        );
      })}
    </>
  );
}

export function KnowledgeCanvasPage() {
  const { t } = useI18n();
  const [mode, setMode] = useState<'dom' | 'echarts'>('dom');
  // A6 (DEV-0188): 节点位置上提到页面级 — 边层 SVG 与画布 world 尺寸随节点位置动态扩张
  const [positions, setPositions] = useState<PositionMap>(() => {
    const m: PositionMap = {};
    for (const n of DEMO_NODES) m[n.id] = { x: n.x ?? 0, y: n.y ?? 0 };
    return m;
  });
  const bounds = useMemo(() => {
    let maxX = 0;
    let maxY = 0;
    for (const p of Object.values(positions)) {
      maxX = Math.max(maxX, p.x);
      maxY = Math.max(maxY, p.y);
    }
    // 基础域 = DEMO 初始布局域; 拖出后 +200px 边距扩张
    return { w: Math.max(1400, maxX + 200), h: Math.max(800, maxY + 200) };
  }, [positions]);

  const option = useMemo(
    () => ({
      tooltip: {
        formatter: (params: { dataType?: string; data?: { name?: string } }) => {
          if (params.dataType === 'node') {
            return params.data?.name ?? '';
          }
          return '';
        },
      },
      legend: [
        {
          data: DEMO_CATEGORIES.map((c) => c.name),
          top: 16,
          left: 'center',
          textStyle: { fontSize: 11, color: 'var(--ink-2)' },
        },
      ],
      animationDurationUpdate: 600,
      animationEasingUpdate: 'quinticInOut',
      series: [
        {
          type: 'graph',
          layout: 'none',
          roam: true,
          draggable: true,
          focusNodeAdjacency: true,
          symbolSize: 50,
          edgeSymbol: ['none', 'none'],
          label: {
            show: true,
            position: 'right',
            color: 'var(--ink)',
            fontSize: 12,
          },
          lineStyle: {
            color: 'var(--border-color)',
            curveness: 0.2,
            width: 1.5,
          },
          emphasis: {
            focus: 'adjacency',
            lineStyle: { width: 2.5 },
          },
          categories: DEMO_CATEGORIES.map((c) => ({ name: c.name })),
          data: DEMO_NODES,
          links: DEMO_EDGES,
        },
      ],
    }),
    [],
  );

  return (
    <div className="px-6 py-8 max-w-7xl mx-auto" data-testid="knowledge-canvas-root">
      <header className="mb-6" style={{ display: 'flex', alignItems: 'baseline', justifyContent: 'space-between', gap: 16, flexWrap: 'wrap' }}>
        <div>
          <h1 className="text-2xl font-semibold mb-1" style={{ color: 'var(--ink)' }}>
            {t('canvas.title')}
          </h1>
          <p className="text-sm" style={{ color: 'var(--ink-2)' }}>
            {t('canvas.subtitle')}
          </p>
        </div>
        <div role="group" aria-label="画布模式切换" style={{ display: 'flex', gap: 6 }}>
          <button
            type="button"
            className={`btn-secondary${mode === 'dom' ? ' active' : ''}`}
            style={mode === 'dom' ? { borderColor: 'var(--accent)', color: 'var(--accent)' } : undefined}
            aria-pressed={mode === 'dom'}
            onClick={() => setMode('dom')}
          >
            画布模式
          </button>
          <button
            type="button"
            className={`btn-secondary${mode === 'echarts' ? ' active' : ''}`}
            style={mode === 'echarts' ? { borderColor: 'var(--accent)', color: 'var(--accent)' } : undefined}
            aria-pressed={mode === 'echarts'}
            onClick={() => setMode('echarts')}
          >
            印厂 demo (ECharts)
          </button>
        </div>
      </header>

      {/* Demo 说明卡 */}
      <div
        className="mb-4 px-4 py-2 rounded text-xs font-mono flex items-center gap-3"
        style={{
          background: 'var(--bg-warning)',
          color: 'var(--text-on-warning)',
          border: '1px solid var(--border-color)',
        }}
      >
        <span data-testid="canvas-demo-note">ℹ️ {t('canvas.demoNote')}</span>
      </div>

      {mode === 'dom' ? (
        <InfiniteCanvas height={640} worldWidth={bounds.w} worldHeight={bounds.h} ariaLabel="知识画布 (拖拽空白平移, 滚轮缩放, 双击重置)">
          <CanvasModeGraph positions={positions} setPositions={setPositions} width={bounds.w} height={bounds.h} />
        </InfiniteCanvas>
      ) : (
        <div
          className="rounded-lg overflow-hidden"
          style={{
            background: 'var(--bg-card)',
            border: '1px solid var(--border-color)',
            height: '640px',
          }}
        >
          <ReactECharts
            option={option}
            style={{ height: '100%', width: '100%' }}
            opts={{ renderer: 'canvas' }}
          />
        </div>
      )}
    </div>
  );
}
