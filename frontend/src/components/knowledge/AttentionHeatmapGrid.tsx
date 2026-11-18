/**
 * AttentionHeatmapGrid — 天数 × 24 小时注意力密度网格 + Tooltip
 * (B5 续拆: 从 AttentionHeatmap 抽出的纯展示区块)
 *
 * 数据由容器传入；悬停 tooltip 是本组件内部状态，不参与取数。
 */
import React, { useState } from 'react';
import {
  GRID_GAP,
  HOURS,
  buildGrid,
  formatShortDate,
  getCellColor,
  type AttentionDataPoint,
  type TooltipState,
} from './attentionModel';

interface AttentionHeatmapGridProps {
  data: AttentionDataPoint[];
  dates: string[];
  days: number;
  cellSize: number;
  labelColWidth: number;
  headerRowHeight: number;
}

export function AttentionHeatmapGrid({
  data,
  dates,
  days,
  cellSize,
  labelColWidth,
  headerRowHeight,
}: AttentionHeatmapGridProps) {
  const [tooltip, setTooltip] = useState<TooltipState | null>(null);

  const grid = buildGrid(dates, data);
  const maxCount = Math.max(1, ...grid.values());

  const handleCellClick = (_date: string) => {
    // 原 /knowledge/briefing?date= 路由已在 v0.7.0 删除 (死链)。
    // 日期维度的下钻列表页尚未实现 (数据源 /api/attention/events)，
    // 在此之前不导航避免死链; 数据细节由悬浮 tooltip 呈现。
  };

  const handleCellEnter = (
    e: React.MouseEvent,
    date: string,
    hour: number,
    count: number,
  ) => {
    setTooltip({ date, hour, count, x: e.clientX, y: e.clientY });
  };

  const handleCellLeave = () => {
    setTooltip(null);
  };

  return (
    /* 外容器：支持水平滚动 */
    <div className="relative" style={{ overflowX: 'auto' }}>
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: `${labelColWidth}px repeat(${HOURS}, ${cellSize}px)`,
          gridTemplateRows: `${headerRowHeight}px repeat(${days}, ${cellSize}px)`,
          gap: `${GRID_GAP}px`,
          width: 'fit-content',
        }}
      >
        {/* 左上角空位 */}
        <div style={{ gridRow: 1, gridColumn: 1 }} />

        {/* X 轴：小时标签 0-23 */}
        {Array.from({ length: HOURS }, (_, h) => (
          <div
            key={`x-${h}`}
            style={{
              gridRow: 1,
              gridColumn: h + 2,
              fontSize: 8,
              color: 'var(--text-muted)',
              textAlign: 'center',
              lineHeight: `${headerRowHeight}px`,
              fontFamily: 'var(--font-mono)',
            }}
          >
            {h}
          </div>
        ))}

        {/* Y 轴：日期标签 + 单元格行 */}
        {dates.map((date, rowIdx) => (
          <React.Fragment key={date}>
            {/* 日期标签 */}
            <div
              style={{
                gridRow: rowIdx + 2,
                gridColumn: 1,
                fontSize: 8,
                color: 'var(--text-secondary)',
                lineHeight: `${cellSize}px`,
                paddingRight: 4,
                textAlign: 'right',
                whiteSpace: 'nowrap',
                fontFamily: 'var(--font-mono)',
              }}
            >
              {formatShortDate(date)}
            </div>

            {/* 24 个单元格 */}
            {Array.from({ length: HOURS }, (_, hour) => {
              const count = grid.get(`${date}|${hour}`) || 0;
              const active = count > 0;
              const isHovered =
                tooltip?.date === date && tooltip?.hour === hour;

              return (
                <div
                  key={`${date}-${hour}`}
                  data-cell={`${date}|${hour}`}
                  style={{
                    gridRow: rowIdx + 2,
                    gridColumn: hour + 2,
                    width: cellSize,
                    height: cellSize,
                    borderRadius: 2,
                    backgroundColor: active
                      ? getCellColor(count, maxCount)
                      : 'var(--border-subtle)',
                    outline: isHovered
                      ? '1.5px solid var(--color-info)'
                      : 'none',
                    outlineOffset: -1,
                    transition: 'outline 100ms ease',
                  }}
                  onClick={() => handleCellClick(date)}
                  onMouseEnter={(e) =>
                    handleCellEnter(e, date, hour, count)
                  }
                  onMouseLeave={handleCellLeave}
                />
              );
            })}
          </React.Fragment>
        ))}
      </div>

      {/* Tooltip */}
      {tooltip && (
        <div
          style={{
            position: 'fixed',
            left: tooltip.x,
            top: tooltip.y - 8,
            transform: 'translate(-50%, -100%)',
            backgroundColor: 'var(--bg-elevated)',
            border: '1px solid var(--border-color)',
            borderRadius: 'var(--radius-sm)',
            padding: '4px 8px',
            fontSize: 10,
            color: 'var(--text-primary)',
            whiteSpace: 'nowrap',
            zIndex: 700,
            pointerEvents: 'none',
            fontFamily: 'var(--font-mono)',
            lineHeight: 1.4,
          }}
        >
          {tooltip.date}{' '}
          {String(tooltip.hour).padStart(2, '0')}:00 —{' '}
          {tooltip.count} 次
        </div>
      )}
    </div>
  );
}
