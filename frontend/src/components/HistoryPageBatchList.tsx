// HistoryPageBatchList — 从 HistoryPage.tsx 拆出的左侧批次列表 (纯搬迁, 行为不变).
// 职责: 批次 sticky 侧栏 (loading / error / 空态 / 批次条目 + 选中态).

import type { Batch } from '../types';
import { EmptyState } from '../primitives/EmptyState';
import { formatBatchRange } from './HistoryPageParts';

interface HistoryPageBatchListProps {
  batches: Batch[];
  batchesLoading: boolean;
  batchesError: string | null;
  selectedBatchNo: number | null;
  onSelectBatch: (batchNo: number) => void;
}

export function HistoryPageBatchList({
  batches, batchesLoading, batchesError, selectedBatchNo, onSelectBatch,
}: HistoryPageBatchListProps) {
  return (
    <aside
      className="shrink-0 hidden md:block"
      style={{
        width: 240,
        position: 'sticky',
        top: 16,
        alignSelf: 'flex-start',
        maxHeight: 'calc(100vh - 32px)',
        overflowY: 'auto',
      }}
    >
      <div
        className="rounded-[var(--radius-md)] p-3"
        style={{ backgroundColor: 'var(--bg-elevated)', border: '1px solid var(--border-color)' }}
      >
        <h3 className="text-xs font-bold mb-2" style={{ color: 'var(--text-muted)' }}>
          批次列表 (按时间倒序)
        </h3>
        {batchesLoading && (
          <p className="text-xs py-4 text-center" style={{ color: 'var(--text-muted)' }}>加载中…</p>
        )}
        {batchesError && (
          <div
            className="text-xs py-2.5 px-2 rounded-[var(--radius-sm)]"
            style={{
              backgroundColor: 'color-mix(in srgb, var(--color-error) 12%, transparent)',
              border: '1px solid var(--color-error)',
              color: 'var(--color-error)',
            }}
          >
            加载失败: {batchesError}
          </div>
        )}
        {!batchesLoading && !batchesError && batches.length === 0 && (
          <EmptyState
            compact
            title="暂无历史批次"
            description="项目刚启动, 第 1 批还未结束"
          />
        )}
        <ul className="space-y-1">
          {batches.map(b => {
            const active = b.batch_no === selectedBatchNo;
            return (
              <li key={b.batch_no}>
                <button
                  onClick={() => onSelectBatch(b.batch_no)}
                  className={`w-full text-left px-2.5 py-2 rounded-[var(--radius-sm)] transition-colors ${active ? 'active' : ''}`}
                  style={{
                    backgroundColor: active ? 'var(--bg-hover)' : 'transparent',
                    borderLeft: active ? '3px solid var(--color-ai)' : '3px solid transparent',
                    color: active ? 'var(--text-primary)' : 'var(--text-secondary)',
                  }}
                >
                  <div className="flex items-center justify-between">
                    <span className="text-xs font-bold">第 {b.batch_no} 批</span>
                    <span className="text-[10px]" style={{ color: 'var(--text-muted)' }}>
                      {b.item_count} 条
                    </span>
                  </div>
                  <div className="text-[10px] mt-0.5" style={{ color: 'var(--text-muted)' }}>
                    {formatBatchRange(b.start, b.end)}
                  </div>
                  {b.favorite_count > 0 && (
                    <div className="text-[10px] mt-0.5" style={{ color: 'var(--color-finance)' }}>
                      ⭐ {b.favorite_count} 收藏
                    </div>
                  )}
                </button>
              </li>
            );
          })}
        </ul>
      </div>
    </aside>
  );
}