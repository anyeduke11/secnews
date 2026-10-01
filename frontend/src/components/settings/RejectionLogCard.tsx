/**
 * RejectionLogCard — 拒收日志卡 (2026-10-01 spec §6, 设置→运维第 4 卡)。
 *
 * 数据: GET /api/quality/rejection-log (分页, 复用原 QualityRejectionPage 的
 * 查询形态)。reason 列双层解释: explain (LLM 人话) 有则首行显示;
 * 词典 flag 标签 (rejectionReasons) 恒显小字, 首项为主拒因 (data-main-flag)。
 */
import { useCallback, useEffect, useState } from 'react';
import { LayerTable, type LayerTableColumn } from '../layout/LayerTable';
import { getJSON } from '../../lib/api';
import { parseRejectionFlags, flagLabel } from '../../lib/rejectionReasons';

interface RejectionLogItem {
  id: number;
  source_id: string;
  item_title: string;
  item_url: string;
  rejected_by: string;
  reason: string;
  explain: string | null;
  created_at: string;
}

const PAGE_SIZE = 20;

export function RejectionLogCard() {
  const [items, setItems] = useState<RejectionLogItem[] | null>(null);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);

  const reload = useCallback(async (p: number) => {
    try {
      const d = await getJSON<{ total: number; items: RejectionLogItem[] }>(
        `/api/quality/rejection-log?page=${p}&page_size=${PAGE_SIZE}`,
      );
      setItems(d.items ?? []);
      setTotal(d.total ?? 0);
    } catch {
      setItems([]);
    }
  }, []);

  useEffect(() => { void reload(page); }, [page, reload]);

  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));

  const columns: LayerTableColumn<RejectionLogItem>[] = [
    { key: 'created_at', header: '时间', render: row => (
      <span className="text-xs whitespace-nowrap" style={{ color: 'var(--text-muted)' }}>
        {row.created_at?.slice(5, 16)}
      </span>
    ) },
    { key: 'source_id', header: '来源', render: row => (
      <span className="max-w-[120px] truncate inline-block" title={row.source_id}>
        {row.source_id}
      </span>
    ) },
    { key: 'item_title', header: '标题', render: row => (
      <a href={row.item_url} target="_blank" rel="noopener noreferrer"
         className="max-w-[240px] truncate inline-block hover:underline">
        {row.item_title}
      </a>
    ) },
    { key: 'reason', header: '拒收原因', render: row => (
      <div className="max-w-[280px]">
        {row.explain && (
          <div className="text-xs" style={{ color: 'var(--text-primary)' }}>
            {row.explain}
          </div>
        )}
        <div className="flex flex-wrap gap-1 text-[10px]"
             style={{ color: 'var(--text-muted)' }}>
          {parseRejectionFlags(row.reason).map((f, i) => (
            <span key={f} data-main-flag={i === 0 || undefined}
                  style={{ fontWeight: i === 0 ? 600 : 400 }}>
              {flagLabel(f)}
            </span>
          ))}
        </div>
      </div>
    ) },
  ];

  return (
    <div className="st-card">
      <h3>拒收日志</h3>
      <p className="st-raildesc">
        采集质量门禁的拒收审计 · 每轮采集后自动生成解释
      </p>
      {items === null ? (
        <p className="st-raildesc">载入中…</p>
      ) : items.length === 0 ? (
        <p className="st-raildesc">暂无拒收记录。</p>
      ) : (
        <>
          <LayerTable
            columns={columns}
            data={items}
            rowKey={row => row.id}
            emptyMessage="暂无拒收记录"
            compact
          />
          <div className="flex items-center justify-end gap-2 mt-2">
            <button
              type="button"
              className="st-btn ghost"
              disabled={page <= 1}
              onClick={() => setPage(p => Math.max(1, p - 1))}
            >
              上一页
            </button>
            <span className="text-xs font-mono tabular-nums" style={{ color: 'var(--text-muted)' }}>
              {page} / {totalPages} · 共 {total} 条
            </span>
            <button
              type="button"
              className="st-btn ghost"
              disabled={page >= totalPages}
              onClick={() => setPage(p => Math.min(totalPages, p + 1))}
            >
              下一页
            </button>
          </div>
        </>
      )}
    </div>
  );
}
