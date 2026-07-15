import React, { useState, useEffect } from 'react';
import ReactECharts from 'echarts-for-react';
import type { ConceptProgress } from '../types';

export function MasteryGauge() {
  const [progress, setProgress] = useState<ConceptProgress[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetch('/api/knowledge/progress')
      .then(r => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        return r.json();
      })
      .then(data => {
        setProgress(data.progress || []);
        setLoading(false);
      })
      .catch(e => {
        setError(e?.message || String(e));
        setLoading(false);
      });
  }, []);

  if (loading) {
    return <p className="text-xs" style={{ color: 'var(--text-muted)' }}>加载中…</p>;
  }

  if (error) {
    return <p className="text-xs" style={{ color: '#e85d5d' }}>加载失败: {error}</p>;
  }

  if (progress.length === 0) {
    return (
      <p className="text-xs" style={{ color: 'var(--text-muted)' }}>
        暂无掌握度数据。请先编译知识库。
      </p>
    );
  }

  const avgMastery = Math.round(
    progress.reduce((sum, p) => sum + (p.mastery || 0), 0) / progress.length
  );

  const option = {
    series: [{
      type: 'gauge',
      radius: '90%',
      startAngle: 200,
      endAngle: -20,
      min: 0,
      max: 100,
      progress: {
        show: true,
        width: 10,
        itemStyle: { color: 'var(--color-ai)' },
      },
      axisLine: {
        lineStyle: { width: 10, color: [[1, 'var(--bg-hover)']] },
      },
      pointer: { show: false },
      axisTick: { show: false },
      splitLine: { show: false },
      axisLabel: { show: false },
      anchor: { show: false },
      title: { show: false },
      detail: {
        valueAnimation: true,
        offsetCenter: [0, '10%'],
        fontSize: 20,
        fontWeight: 'bold',
        color: 'var(--text-primary)',
        formatter: '{value}%',
      },
      data: [{ value: avgMastery }],
    }],
  };

  return (
    <div>
      <ReactECharts option={option} style={{ height: '140px', width: '100%' }} />
      <div className="space-y-1 mt-2 max-h-40 overflow-auto">
        {progress.map(p => (
          <div key={p.concept_slug} className="flex items-center gap-2 text-[10px]">
            <span
              className="truncate"
              style={{ color: 'var(--text-primary)', minWidth: '60px', maxWidth: '100px' }}
              title={p.title}
            >
              {p.title}
            </span>
            <div className="flex-1 rounded-full" style={{ backgroundColor: 'var(--bg-hover)', height: '4px' }}>
              <div
                className="rounded-full"
                style={{
                  width: `${Math.min(p.mastery, 100)}%`,
                  height: '4px',
                  backgroundColor: p.mastery >= 80 ? '#00c96a' : p.mastery >= 50 ? '#f0c929' : '#e85d5d',
                }}
              />
            </div>
            <span style={{ color: 'var(--text-muted)', minWidth: '28px', textAlign: 'right' }}>
              {p.mastery}%
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}
