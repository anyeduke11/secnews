/**
 * AttentionHeatmap — 注意力度热力图 (Phase 17)
 *
 * 30 天 × 24 小时的注意力密度网格。
 * 每个单元格代表该小时/该日的注意力事件计数。
 *
 * 数据来源: GET /api/attention/events?days=30
 * 若端点不存在，降级展示空网格。
 */
import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { Icon } from '../Icon';

// ── 类型 ────────────────────────────────────────────────────

interface AttentionDataPoint {
  date: string;
  hour: number;
  count: number;
}

interface TooltipState {
  date: string;
  hour: number;
  count: number;
  x: number;
  y: number;
}

// ── 常量 ────────────────────────────────────────────────────

const HOURS = 24;
const CELL_SIZE = 12;
const CELL_SIZE_COMPACT = 8;
const GRID_GAP = 2;
const LABEL_COL_WIDTH = 64;
const LABEL_COL_WIDTH_COMPACT = 52;
const HEADER_ROW_HEIGHT = 20;
const HEADER_ROW_HEIGHT_COMPACT = 16;

// ── 工具函数 ────────────────────────────────────────────────

/** 生成最近 N 天的日期字符串数组 (YYYY-MM-DD) */
function getLastDays(n: number): string[] {
  const result: string[] = [];
  const today = new Date();
  for (let i = n - 1; i >= 0; i--) {
    const d = new Date(today);
    d.setDate(d.getDate() - i);
    const y = d.getFullYear();
    const m = String(d.getMonth() + 1).padStart(2, '0');
    const day = String(d.getDate()).padStart(2, '0');
    result.push(`${y}-${m}-${day}`);
  }
  return result;
}

/** 格式化日期为 "Mon 7/14" 样式 */
function formatShortDate(dateStr: string): string {
  const d = new Date(dateStr + 'T00:00:00');
  const dayNames = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];
  return `${dayNames[d.getDay()]} ${d.getMonth() + 1}/${d.getDate()}`;
}

/**
 * 根据 count / maxCount 比率计算单元格颜色。
 * 0 → 透明底 (border-subtle)
 * 低 → 浅橙 hsl(28, 70%, 58%)
 * 高 → 深红 hsl(0, 100%, 30%)
 */
function getCellColor(count: number, maxCount: number): string {
  if (count === 0) return 'transparent';
  const t = Math.min(count / maxCount, 1);
  const hue = Math.round(28 - t * 28);
  const sat = Math.round(70 + t * 30);
  const lit = Math.round(58 - t * 28);
  return `hsl(${hue}, ${sat}%, ${lit}%)`;
}

// ── 组件 ────────────────────────────────────────────────────

interface AttentionHeatmapProps {
  compact?: boolean;
}

export function AttentionHeatmap({ compact = false }: AttentionHeatmapProps) {
  const navigate = useNavigate();
  const [data, setData] = useState<AttentionDataPoint[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [tooltip, setTooltip] = useState<TooltipState | null>(null);

  const DAYS = compact ? 14 : 30;
  const cellSize = compact ? CELL_SIZE_COMPACT : CELL_SIZE;
  const labelColWidth = compact ? LABEL_COL_WIDTH_COMPACT : LABEL_COL_WIDTH;
  const headerRowHeight = compact ? HEADER_ROW_HEIGHT_COMPACT : HEADER_ROW_HEIGHT;
  const dates = getLastDays(DAYS);
  const dateRange = `${dates[0]} ~ ${dates[dates.length - 1]}`;

  // ── 数据获取 ──────────────────────────────────────────────

  useEffect(() => {
    setLoading(true);
    setError(null);
    fetch('/api/attention/events?days=30')
      .then(r => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        return r.json();
      })
      .then(json => {
        const points: AttentionDataPoint[] = Array.isArray(json)
          ? json
          : (json.events || json.data || []);
        setData(points);
        setLoading(false);
      })
      .catch(e => {
        // 端点可能不存在，降级展示空网格
        setError(e?.message || String(e));
        setLoading(false);
      });
  }, []);

  // ── 构建 30×24 网格 ───────────────────────────────────────

  const grid = new Map<string, number>();
  for (const date of dates) {
    for (let h = 0; h < HOURS; h++) {
      grid.set(`${date}|${h}`, 0);
    }
  }
  for (const point of data) {
    const key = `${point.date}|${point.hour}`;
    if (grid.has(key)) {
      grid.set(key, point.count);
    }
  }

  const maxCount = Math.max(1, ...grid.values());
  const hasData = data.length > 0;

  // ── 事件处理 ──────────────────────────────────────────────

  const handleCellClick = (date: string) => {
    navigate(`/knowledge/briefing?date=${date}`);
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

  // ── 渲染 ──────────────────────────────────────────────────

  return (
    <div
      className="rounded-[var(--radius-md)] p-3"
      style={{
        backgroundColor: 'var(--bg-elevated)',
        border: '1px solid var(--border-color)',
      }}
    >
      {/* 标题区 */}
      <div className="flex items-center gap-2 mb-2.5">
        <div
          className="w-7 h-7 rounded-md flex items-center justify-center shrink-0"
          style={{
            backgroundColor: 'color-mix(in srgb, var(--color-info) 12%, transparent)',
            color: 'var(--color-info)',
          }}
        >
          <Icon size={14}>
            <polyline points="22 12 18 12 15 21 9 3 6 12 2 12" />
          </Icon>
        </div>
        <div className="flex-1 min-w-0">
          <h3
            className="text-sm font-bold leading-tight"
            style={{ color: 'var(--text-primary)' }}
          >
            注意力度热力图
          </h3>
          <p className="text-[10px]" style={{ color: 'var(--text-muted)' }}>
            {dateRange}
          </p>
        </div>
      </div>

      {/* 加载态 */}
      {loading && (
        <div className="flex items-center justify-center py-8">
          <div
            className="rounded-full animate-spin"
            style={{
              width: 18,
              height: 18,
              border: '2px solid var(--border-color)',
              borderTopColor: 'var(--color-info)',
            }}
          />
        </div>
      )}

      {/* 网格 (加载完成后始终渲染) */}
      {!loading && (
        <>
          {/* 状态提示 */}
          {error && (
            <p
              className="text-[10px] mb-1.5"
              style={{ color: 'var(--text-muted)' }}
            >
              无法加载注意力数据
            </p>
          )}
          {!error && !hasData && (
            <p
              className="text-[10px] mb-1.5"
              style={{ color: 'var(--text-muted)' }}
            >
              暂无注意力数据
            </p>
          )}

          {/* 外容器：支持水平滚动 */}
          <div className="relative" style={{ overflowX: 'auto' }}>
            <div
              style={{
                display: 'grid',
                gridTemplateColumns: `${labelColWidth}px repeat(${HOURS}, ${cellSize}px)`,
                gridTemplateRows: `${headerRowHeight}px repeat(${DAYS}, ${cellSize}px)`,
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
                        style={{
                          gridRow: rowIdx + 2,
                          gridColumn: hour + 2,
                          width: cellSize,
                          height: cellSize,
                          borderRadius: 2,
                          backgroundColor: active
                            ? getCellColor(count, maxCount)
                            : 'var(--border-subtle)',
                          cursor: 'pointer',
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
        </>
      )}
    </div>
  );
}