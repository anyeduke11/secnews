/**
 * KnowledgeGraph — 知识图谱（ECharts force layout）。
 *
 * Phase 3: 节点色按 domain 走 token, 暗/亮主题自动切换。
 *          通过 useThemeColors 读取 ECharts 所需的字面色值。
 */
import React, { useState, useEffect, useMemo } from 'react';
import ReactECharts from 'echarts-for-react';
import type { GraphData } from '../types';
import { useThemeColors, ThemeColorKey } from '../hooks/useThemeColors';
import { EmptyState } from './EmptyState';

interface KnowledgeGraphProps {
  domain?: string;
  onSelectConcept?: (slug: string) => void;
}

/** 知识图谱 domain → token key 映射 */
const DOMAIN_TOKEN: Record<string, ThemeColorKey> = {
  security: 'color-security',
  ai: 'color-ai',
  finance: 'color-finance',
  product: 'color-warning',
  engineering: 'color-ai',
  business: 'color-startup',
  design: 'color-info',
};
const FALLBACK_TOKEN: ThemeColorKey = 'text-muted';

export function KnowledgeGraph({ domain, onSelectConcept }: KnowledgeGraphProps) {
  const [data, setData] = useState<GraphData>({ nodes: [], edges: [] });
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    const params = domain ? `?domain=${encodeURIComponent(domain)}` : '';
    fetch(`/api/knowledge/graph${params}`)
      .then(r => r.json())
      .then(d => {
        setData(d || { nodes: [], edges: [] });
        setLoading(false);
      })
      .catch(() => setLoading(false));
  }, [domain]);

  // 读取需要用到的所有 token
  const colors = useThemeColors([
    'text-primary',
    'text-muted',
    'color-security',
    'color-ai',
    'color-finance',
    'color-warning',
    'color-startup',
    'color-info',
  ]);

  // 解析 domain → 字面色
  const domainColor = (d: string | null): string => {
    const key = DOMAIN_TOKEN[d || ''] || FALLBACK_TOKEN;
    return colors[key] || 'var(--text-muted)';
  };

  const option = useMemo(
    () => ({
      tooltip: {
        formatter: (params: any) => {
          if (params.dataType === 'node') {
            return `${params.data.name} (${params.data.value || 0} 条)`;
          }
          return `${params.data.source} → ${params.data.target}`;
        },
      },
      series: [
        {
          type: 'graph',
          layout: 'force',
          roam: true,
          draggable: true,
          force: {
            repulsion: 100,
            edgeLength: 80,
            gravity: 0.1,
          },
          label: {
            show: true,
            position: 'right',
            fontSize: 10,
            color: colors['text-primary'] || 'var(--text-primary)',
          },
          data: data.nodes.map((n) => {
            const isLocal = n.wiki === 'local';
            const color = domainColor(n.domain);
            // Hotspot=实心 / Local=空心 (borderColor + transparent bg)
            const itemStyle = isLocal
              ? { borderColor: color, borderWidth: 2, color: 'transparent' }
              : { color };
            return {
              id: n.id,
              name: n.label,
              value: n.count,
              symbolSize: Math.log(n.count + 1) * 10 + 15,
              category: n.domain || 'unknown',
              itemStyle,
            };
          }),
          edges: data.edges.map((e) => {
            const isFederated = e.type === 'federated';
            return {
              source: e.source,
              target: e.target,
              value: e.weight,
              lineStyle: {
                width: Math.min(e.weight, 5),
                ...(isFederated ? { type: 'dashed' as const } : {}),
              },
            };
          }),
          emphasis: {
            focus: 'adjacency',
            lineStyle: { width: 4 },
          },
        },
      ],
    }),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [data, colors],
  );

  if (loading) {
    return (
      <div
        className="flex items-center justify-center"
        style={{ height: '300px', color: 'var(--text-muted)' }}
      >
        <p className="text-xs">加载中…</p>
      </div>
    );
  }

  if (data.nodes.length === 0) {
    return (
      <div
        className="flex items-center justify-center rounded-[var(--radius-sm)]"
        style={{ height: '300px', backgroundColor: 'var(--bg-hover)' }}
      >
        <EmptyState
          compact
          title="暂无概念"
          description="请先编译知识库"
        />
      </div>
    );
  }

  return (
    <ReactECharts
      option={option}
      style={{ height: '300px', width: '100%' }}
      onEvents={{
        click: (params: any) => {
          if (params.dataType === 'node' && onSelectConcept) {
            onSelectConcept(params.data.id);
          }
        },
      }}
    />
  );
}
