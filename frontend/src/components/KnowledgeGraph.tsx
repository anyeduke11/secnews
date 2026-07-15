import React, { useState, useEffect } from 'react';
import ReactECharts from 'echarts-for-react';
import type { GraphData } from '../types';

interface KnowledgeGraphProps {
  domain?: string;
  onSelectConcept?: (slug: string) => void;
}

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

  const option = {
    tooltip: {
      formatter: (params: any) => {
        if (params.dataType === 'node') {
          return `${params.data.name} (${params.data.value || 0} 条)`;
        }
        return `${params.data.source} → ${params.data.target}`;
      },
    },
    series: [{
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
        color: 'var(--text-primary)',
      },
      data: data.nodes.map(n => ({
        id: n.id,
        name: n.label,
        value: n.count,
        symbolSize: Math.log(n.count + 1) * 10 + 15,
        category: n.domain || 'unknown',
        itemStyle: { color: _domainColor(n.domain) },
      })),
      edges: data.edges.map(e => ({
        source: e.source,
        target: e.target,
        value: e.weight,
        lineStyle: { width: Math.min(e.weight, 5) },
      })),
      emphasis: {
        focus: 'adjacency',
        lineStyle: { width: 4 },
      },
    }],
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center" style={{ height: '300px', color: 'var(--text-muted)' }}>
        <p className="text-xs">加载中…</p>
      </div>
    );
  }

  if (data.nodes.length === 0) {
    return (
      <div className="flex items-center justify-center rounded-[var(--radius-sm)]"
           style={{ height: '300px', backgroundColor: 'var(--bg-hover)', color: 'var(--text-muted)' }}>
        <p className="text-xs">暂无概念。请先编译知识库</p>
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

function _domainColor(domain: string | null): string {
  const colors: Record<string, string> = {
    security: '#e85d5d',
    ai: '#8b5cf6',
    finance: '#10b981',
    product: '#f59e0b',
    engineering: '#3b82f6',
    business: '#ec4899',
    design: '#06b6d4',
  };
  return colors[domain || ''] || '#6b7280';
}
