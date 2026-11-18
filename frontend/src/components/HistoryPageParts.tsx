// HistoryPageParts — 从 HistoryPage.tsx 拆出的纯函数与批次摘要条 (纯搬迁, 行为不变).
// 职责: 批次日期格式化 (formatBatchDate / formatBatchRange) + BatchSummaryBar 元数据条.

import type { BatchSummaryResponse } from '../types';

export function formatBatchDate(isoString: string): string {
  // "2026-07-06T00:00:00+00:00" → "7/6"
  const d = new Date(isoString);
  return `${d.getMonth() + 1}/${d.getDate()}`;
}

export function formatBatchRange(start: string, end: string): string {
  return `${formatBatchDate(start)} - ${formatBatchDate(end)}`;
}

interface BatchSummaryBarProps {
  batchNo: number;
  summary: BatchSummaryResponse;
}

export function BatchSummaryBar({ batchNo, summary }: BatchSummaryBarProps) {
  return (
    <div
      className="rounded-[var(--radius-md)] p-3 mb-3"
      style={{ backgroundColor: 'var(--bg-elevated)', border: '1px solid var(--border-color)' }}
    >
      <div className="flex items-center gap-3 flex-wrap">
        <span className="text-sm font-bold" style={{ color: 'var(--text-primary)' }}>
          第 {batchNo} 批
        </span>
        <span className="text-xs" style={{ color: 'var(--text-muted)' }}>
          {formatBatchRange(summary.start, summary.end)} · 共 {summary.total} 条 · {summary.source_count} 个信源
        </span>
      </div>
      {summary.top_sources.length > 0 && (
        <div className="text-xs mt-1.5" style={{ color: 'var(--text-secondary)' }}>
          Top 信源: {summary.top_sources.map(s => `${s.source}(${s.count})`).join(', ')}
        </div>
      )}
    </div>
  );
}