import React, { useEffect, useState } from 'react';
import { LayerCard } from './layout/LayerCard';
import { LayerTable, type LayerTableColumn } from './layout/LayerTable';
import { LayerBadge } from './layout/LayerBadge';

interface RejectionLogItem {
  id: number;
  source_id: string;
  item_title: string;
  item_url: string;
  rejected_by: string;
  reason: string;
  raw_data: string;
  created_at: string;
}

interface RejectionStats {
  by_gate: { gate_name: string; count: number }[];
  trend: { day: string; count: number }[];
}

export default function QualityRejectionPage() {
  const [items, setItems] = useState<RejectionLogItem[]>([]);
  const [stats, setStats] = useState<RejectionStats | null>(null);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [gateName, setGateName] = useState('');
  const [sourceId, setSourceId] = useState('');
  const [dateFrom, setDateFrom] = useState('');
  const [dateTo, setDateTo] = useState('');
  const [page, setPage] = useState(1);
  const pageSize = 50;

  const fetchData = async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams();
      if (gateName) params.set('gate_name', gateName);
      if (sourceId) params.set('source_id', sourceId);
      if (dateFrom) params.set('date_from', dateFrom);
      if (dateTo) params.set('date_to', dateTo);
      params.set('page', String(page));
      params.set('page_size', String(pageSize));

      const [logRes, statsRes] = await Promise.all([
        fetch(`/api/quality/rejection-log?${params}`),
        fetch(`/api/quality/rejection-stats?${params}`),
      ]);

      const logData = await logRes.json();
      const statsData = await statsRes.json();

      setItems(logData.items || []);
      setTotal(logData.total || 0);
      setStats(statsData);
    } catch (err) {
      console.error('Failed to fetch rejection data:', err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchData();
  }, [page]);

  const handleSearch = () => {
    setPage(1);
    fetchData();
  };

  const totalPages = Math.ceil(total / pageSize);

  // 统一输入框样式
  const inputClass = 'border rounded px-2 py-1 text-sm';
  const inputStyle: React.CSSProperties = {
    borderColor: 'var(--border-color)',
    backgroundColor: 'var(--bg-secondary)',
    color: 'var(--text-primary)',
  };

  const columns: LayerTableColumn<RejectionLogItem>[] = [
    {
      key: 'created_at',
      header: '时间',
      render: (row) => (
        <span className="font-mono tabular-nums whitespace-nowrap" style={{ color: 'var(--text-muted)' }}>
          {row.created_at?.slice(0, 16)}
        </span>
      ),
    },
    {
      key: 'source_id',
      header: 'Source',
      render: (row) => (
        <span className="max-w-[150px] truncate inline-block" title={row.source_id}>
          {row.source_id}
        </span>
      ),
    },
    {
      key: 'item_title',
      header: '标题',
      render: (row) => (
        <span className="max-w-[300px] truncate inline-block" title={row.item_title}>
          {row.item_title}
        </span>
      ),
    },
    {
      key: 'rejected_by',
      header: 'Gate',
      render: (row) => (
        <LayerBadge variant="soft" color="var(--accent-danger, #ef4444)">
          {row.rejected_by}
        </LayerBadge>
      ),
    },
    {
      key: 'reason',
      header: '原因',
      render: (row) => (
        <span className="max-w-[200px] truncate inline-block" style={{ color: 'var(--text-muted)' }} title={row.reason}>
          {row.reason}
        </span>
      ),
    },
  ];

  return (
    <div className="p-4 space-y-4">
      <h1 className="text-xl font-bold" style={{ color: 'var(--text-primary)' }}>
        质量门禁审计视图
      </h1>

      {/* 统计卡片 */}
      {stats && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          <LayerCard variant="compact" titleStyle="none">
            <div className="text-[10px] font-mono uppercase tracking-[0.06em]" style={{ color: 'var(--text-muted)' }}>
              总拒绝数
            </div>
            <div className="text-2xl font-bold font-mono tabular-nums" style={{ color: 'var(--text-primary)' }}>
              {total}
            </div>
          </LayerCard>
          {stats.by_gate.slice(0, 3).map((g) => (
            <LayerCard key={g.gate_name} variant="compact" titleStyle="none">
              <div className="text-[10px] font-mono uppercase tracking-[0.06em] truncate" style={{ color: 'var(--text-muted)' }}>
                {g.gate_name}
              </div>
              <div className="text-2xl font-bold font-mono tabular-nums" style={{ color: 'var(--text-primary)' }}>
                {g.count}
              </div>
            </LayerCard>
          ))}
        </div>
      )}

      {/* 筛选面板 */}
      <LayerCard variant="default" titleStyle="none">
        <div className="flex flex-wrap gap-4 items-end">
          <div>
            <label
              className="block text-[11px] font-mono uppercase tracking-[0.06em] mb-1"
              style={{ color: 'var(--text-muted)' }}
            >
              Gate 名称
            </label>
            <input
              type="text"
              value={gateName}
              onChange={(e) => setGateName(e.target.value)}
              className={inputClass}
              style={inputStyle}
              placeholder="如: strict_mode"
            />
          </div>
          <div>
            <label
              className="block text-[11px] font-mono uppercase tracking-[0.06em] mb-1"
              style={{ color: 'var(--text-muted)' }}
            >
              Source ID
            </label>
            <input
              type="text"
              value={sourceId}
              onChange={(e) => setSourceId(e.target.value)}
              className={inputClass}
              style={inputStyle}
              placeholder="搜索源名称"
            />
          </div>
          <div>
            <label
              className="block text-[11px] font-mono uppercase tracking-[0.06em] mb-1"
              style={{ color: 'var(--text-muted)' }}
            >
              开始日期
            </label>
            <input
              type="date"
              value={dateFrom}
              onChange={(e) => setDateFrom(e.target.value)}
              className={inputClass}
              style={inputStyle}
            />
          </div>
          <div>
            <label
              className="block text-[11px] font-mono uppercase tracking-[0.06em] mb-1"
              style={{ color: 'var(--text-muted)' }}
            >
              结束日期
            </label>
            <input
              type="date"
              value={dateTo}
              onChange={(e) => setDateTo(e.target.value)}
              className={inputClass}
              style={inputStyle}
            />
          </div>
          <button onClick={handleSearch} className="btn-primary">
            筛选
          </button>
        </div>
      </LayerCard>

      {/* 表格 */}
      <LayerTable
        columns={columns}
        data={items}
        rowKey={(row) => row.id}
        loading={loading}
        emptyMessage="暂无拒绝记录"
        zebra
      />

      {/* 分页 */}
      {totalPages > 1 && (
        <div className="flex justify-center items-center gap-2">
          <button
            onClick={() => setPage(Math.max(1, page - 1))}
            disabled={page <= 1}
            className="btn-secondary"
          >
            上一页
          </button>
          <span className="font-mono tabular-nums text-sm" style={{ color: 'var(--text-muted)' }}>
            {page} / {totalPages}
          </span>
          <button
            onClick={() => setPage(Math.min(totalPages, page + 1))}
            disabled={page >= totalPages}
            className="btn-secondary"
          >
            下一页
          </button>
        </div>
      )}
    </div>
  );
}
