/**
 * CveHeatmap — 12×5 SVG 热力图
 *
 * 行 = severity (critical/high/medium/low/none)
 * 列 = week
 * 颜色按 count 渐变 (红→黄→绿)
 */
import { useState, useEffect } from 'react';
import { useCveHeatmap } from '../../hooks/useCveHeatmap';

const SEVERITIES = ['critical', 'high', 'medium', 'low', 'none'] as const;
const SEVERITY_COLORS: Record<string, string> = {
  critical: '#b91c1c',
  high: '#ea580c',
  medium: '#f59e0b',
  low: '#84cc16',
  none: '#e5e7eb',
};

export function CveHeatmap() {
  const { fetchHeatmap } = useCveHeatmap();
  const [data, setData] = useState<{ weeks: string[]; severities: readonly string[]; matrix: number[][] }>({
    weeks: [],
    severities: SEVERITIES,
    matrix: [],
  });

  useEffect(() => {
    fetchHeatmap().then(setData).catch(() => {});
  }, [fetchHeatmap]);

  const { weeks, severities, matrix } = data;

  const cellSize = 28;
  const gap = 2;
  const width = (weeks.length || 12) * (cellSize + gap);
  const height = SEVERITIES.length * (cellSize + gap);

  return (
    <div className="overflow-auto">
      <svg width={width} height={height + 20} className="block">
        {/* header: week labels */}
        {weeks.map((w: string, i: number) => (
          <text
            key={w}
            x={i * (cellSize + gap) + cellSize / 2}
            y={12}
            textAnchor="middle"
            className="text-[10px] fill-gray-500"
            style={{ fontSize: '10px', fill: '#6b7280' }}
          >
            {w.slice(5)}
          </text>
        ))}

        {/* rows */}
        {severities.map((sev: string, rowIdx: number) => {
          const counts = matrix.map((col: number[]) => col[rowIdx] || 0);
          const rowMax = Math.max(...counts, 1);
          return (
            <g key={sev}>
              {counts.map((count: number, colIdx: number) => {
                const intensity = count / rowMax;
                const fill = count === 0 ? '#f3f4f6' : SEVERITY_COLORS[sev] || '#d1d5db';
                const opacity = count === 0 ? 1 : 0.35 + intensity * 0.65;
                return (
                  <rect
                    key={`${sev}-${colIdx}`}
                    x={colIdx * (cellSize + gap)}
                    y={rowIdx * (cellSize + gap) + 20}
                    width={cellSize}
                    height={cellSize}
                    rx={3}
                    fill={fill}
                    opacity={opacity}
                  />
                );
              })}
              <text
                x={-4}
                y={rowIdx * (cellSize + gap) + 20 + cellSize / 2}
                textAnchor="end"
                dominantBaseline="middle"
                style={{ fontSize: '10px', fill: '#374151', textTransform: 'capitalize' }}
              >
                {sev}
              </text>
            </g>
          );
        })}
      </svg>
    </div>
  );
}
