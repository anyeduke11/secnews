import React, { useEffect, useState } from 'react';

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

  return (
    <div className="p-4 space-y-4">
      <h1 className="text-xl font-bold">质量门禁审计视图</h1>

      {/* 统计卡片 */}
      {stats && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <div className="bg-white dark:bg-gray-800 rounded-lg p-4 shadow">
            <div className="text-sm" style={{ color: 'var(--text-muted)' }}>总拒绝数</div>
            <div className="text-2xl font-bold">{total}</div>
          </div>
          {stats.by_gate.slice(0, 3).map((g) => (
            <div key={g.gate_name} className="bg-white dark:bg-gray-800 rounded-lg p-4 shadow">
              <div className="text-sm" style={{ color: 'var(--text-muted)' }}>{g.gate_name}</div>
              <div className="text-2xl font-bold">{g.count}</div>
            </div>
          ))}
        </div>
      )}

      {/* 筛选面板 */}
      <div className="bg-white dark:bg-gray-800 rounded-lg p-4 shadow space-y-2">
        <div className="flex flex-wrap gap-4 items-end">
          <div>
            <label className="block text-sm" style={{ color: 'var(--text-muted)' }}>Gate 名称</label>
            <input
              type="text"
              value={gateName}
              onChange={(e) => setGateName(e.target.value)}
              className="border rounded px-2 py-1 dark:bg-gray-700 dark:border-gray-600"
              placeholder="如: strict_mode"
            />
          </div>
          <div>
            <label className="block text-sm" style={{ color: 'var(--text-muted)' }}>Source ID</label>
            <input
              type="text"
              value={sourceId}
              onChange={(e) => setSourceId(e.target.value)}
              className="border rounded px-2 py-1 dark:bg-gray-700 dark:border-gray-600"
              placeholder="搜索源名称"
            />
          </div>
          <div>
            <label className="block text-sm" style={{ color: 'var(--text-muted)' }}>开始日期</label>
            <input
              type="date"
              value={dateFrom}
              onChange={(e) => setDateFrom(e.target.value)}
              className="border rounded px-2 py-1 dark:bg-gray-700 dark:border-gray-600"
            />
          </div>
          <div>
            <label className="block text-sm" style={{ color: 'var(--text-muted)' }}>结束日期</label>
            <input
              type="date"
              value={dateTo}
              onChange={(e) => setDateTo(e.target.value)}
              className="border rounded px-2 py-1 dark:bg-gray-700 dark:border-gray-600"
            />
          </div>
          <button
            onClick={handleSearch}
            className="px-4 py-1 rounded text-white"
            style={{ backgroundColor: 'var(--accent)' }}
          >
            筛选
          </button>
        </div>
      </div>

      {/* 表格 */}
      <div className="bg-white dark:bg-gray-800 rounded-lg shadow overflow-x-auto">
        {loading ? (
          <div className="p-4 text-center" style={{ color: 'var(--text-muted)' }}>加载中...</div>
        ) : items.length === 0 ? (
          <div className="p-4 text-center" style={{ color: 'var(--text-muted)' }}>暂无拒绝记录</div>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b dark:border-gray-700 bg-gray-50 dark:bg-gray-900">
                <th className="px-3 py-2 text-left">时间</th>
                <th className="px-3 py-2 text-left">Source</th>
                <th className="px-3 py-2 text-left">标题</th>
                <th className="px-3 py-2 text-left">拒绝 Gate</th>
                <th className="px-3 py-2 text-left">原因</th>
              </tr>
            </thead>
            <tbody>
              {items.map((item) => (
                <tr key={item.id} className="border-b dark:border-gray-700 hover:bg-gray-50 dark:hover:bg-gray-700">
                  <td className="px-3 py-2 whitespace-nowrap" style={{ color: 'var(--text-muted)' }}>
                    {item.created_at?.slice(0, 16)}
                  </td>
                  <td className="px-3 py-2 max-w-[150px] truncate" title={item.source_id}>
                    {item.source_id}
                  </td>
                  <td className="px-3 py-2 max-w-[300px] truncate" title={item.item_title}>
                    {item.item_title}
                  </td>
                  <td className="px-3 py-2">
                    <span className="bg-red-100 dark:bg-red-900 text-red-700 dark:text-red-300 px-2 py-0.5 rounded text-xs">
                      {item.rejected_by}
                    </span>
                  </td>
                  <td className="px-3 py-2 max-w-[200px] truncate" style={{ color: 'var(--text-muted)' }} title={item.reason}>
                    {item.reason}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {/* 分页 */}
      {totalPages > 1 && (
        <div className="flex justify-center gap-2">
          <button
            onClick={() => setPage(Math.max(1, page - 1))}
            disabled={page <= 1}
            className="px-3 py-1 border rounded disabled:opacity-50"
          >
            上一页
          </button>
          <span className="px-3 py-1">
            {page} / {totalPages}
          </span>
          <button
            onClick={() => setPage(Math.min(totalPages, page + 1))}
            disabled={page >= totalPages}
            className="px-3 py-1 border rounded disabled:opacity-50"
          >
            下一页
          </button>
        </div>
      )}
    </div>
  );
}