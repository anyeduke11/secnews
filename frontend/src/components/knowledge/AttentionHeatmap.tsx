/**
 * AttentionHeatmap — 注意力度热力图 (Phase 17)
 *
 * 30 天 × 24 小时的注意力密度网格。
 * 每个单元格代表该小时/该日的注意力事件计数。
 *
 * 数据来源: GET /api/attention/events?days=30
 * 若端点不存在，降级展示空网格。
 */
import { useState, useEffect } from 'react';
import { Icon } from '../../primitives/Icon';
import { listAttentionEvents } from '../../api/knowledge';
import { useAbortGuard } from '../../hooks/useAbortGuard';
import { AttentionHeatmapGrid } from './AttentionHeatmapGrid';
import {
  CELL_SIZE,
  CELL_SIZE_COMPACT,
  HEADER_ROW_HEIGHT,
  HEADER_ROW_HEIGHT_COMPACT,
  LABEL_COL_WIDTH,
  LABEL_COL_WIDTH_COMPACT,
  getLastDays,
  type AttentionDataPoint,
  type AttentionEventsResponse,
} from './attentionModel';

interface AttentionHeatmapProps {
  compact?: boolean;
}

export function AttentionHeatmap({ compact = false }: AttentionHeatmapProps) {
  const [data, setData] = useState<AttentionDataPoint[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const dead = useAbortGuard(); // P1-7 竞态守卫: 卸载后不写状态

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
    // 非 2xx 由 apiFetch 抛错 → 降级展示空网格 (与原 `HTTP ${status}` 抛错同路径)
    listAttentionEvents<AttentionEventsResponse>(30)
      .then(json => {
        if (dead.current) return;
        const points: AttentionDataPoint[] = Array.isArray(json)
          ? json
          : (json.events || json.data || []);
        setData(points);
        setLoading(false);
      })
      .catch(e => {
        if (dead.current) return;
        // 端点可能不存在，降级展示空网格
        setError(e?.message || String(e));
        setLoading(false);
      });
  }, []);

  const hasData = data.length > 0;

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

          <AttentionHeatmapGrid
            data={data}
            dates={dates}
            days={DAYS}
            cellSize={cellSize}
            labelColWidth={labelColWidth}
            headerRowHeight={headerRowHeight}
          />
        </>
      )}
    </div>
  );
}
