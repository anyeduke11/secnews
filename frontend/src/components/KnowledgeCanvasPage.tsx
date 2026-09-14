/**
 * NAV4 P3 (2026-09-13, DEV-0178): 无限画布 /knowledge/canvas
 *
 * 纯前端 demo (ECharts roam=true + draggable=true):
 * - 8 mock 节点 (代码运行 / 部署 / 监控 等抽象节点)
 * - 用户可拖拽节点、滚轮缩放、滚屏平移
 * - 顶部说明卡标注「Demo 演示 — 真实知识图谱请见 /knowledge/graph」
 *
 * 与 /knowledge/graph 区别: 该页是 ECharts force layout, 本页是 free-form 节点演示,
 *  给 owner 一个"知识库附加视图"占位.
 */

import ReactECharts from 'echarts-for-react';
import { useMemo } from 'react';
import { useI18n } from '../contexts/I18nContext';

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

export function KnowledgeCanvasPage() {
  const { t } = useI18n();

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
      <header className="mb-6">
        <h1 className="text-2xl font-semibold mb-1" style={{ color: 'var(--ink)' }}>
          {t('canvas.title')}
        </h1>
        <p className="text-sm" style={{ color: 'var(--ink-2)' }}>
          {t('canvas.subtitle')}
        </p>
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
    </div>
  );
}