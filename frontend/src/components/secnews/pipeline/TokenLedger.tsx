/**
 * TokenLedger — Token 消耗台账表
 *
 * 自获取模式：调用 /api/kl/pipeline/stats 获取 ledger 数据。
 */
import { useState, useEffect } from 'react';
import { SecNewsHeader } from '../layout/SecNewsHeader';

interface LedgerRow {
  model: string;
  provider?: string;
  calls?: number;
  total_tokens?: number;
  total_prompt?: number;
  total_completion?: number;
}

export function TokenLedger() {
  const [ledger, setLedger] = useState<LedgerRow[]>([]);
  const [loading, setLoading] = useState(true);

  const fetchData = async () => {
    setLoading(true);
    try {
      const res = await fetch('/api/kl/pipeline/stats');
      if (res.ok) {
        const data = await res.json();
        setLedger(data.ledger ?? []);
      }
    } catch {
      setLedger([]);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { fetchData(); }, []);

  return (
    <div>
      <SecNewsHeader title="Token 台账" onRefresh={fetchData} refreshing={loading} />
      {loading && ledger.length === 0 ? (
        <div className="text-sm py-8 text-center" style={{ color: 'var(--text-muted)' }}>加载中...</div>
      ) : ledger.length === 0 ? (
        <div className="p-3 rounded-[var(--radius-sm)]" style={{ border: '1px solid var(--border-color)' }}>
          <p className="text-xs" style={{ color: 'var(--text-muted)' }}>暂无消耗记录</p>
        </div>
      ) : (
        <div className="p-3 rounded-[var(--radius-sm)]" style={{ border: '1px solid var(--border-color)' }}>
          <table className="w-full text-[10px] font-mono">
            <thead>
              <tr style={{ color: 'var(--text-muted)' }}>
                <th className="text-left py-1">模型</th>
                <th className="text-right py-1">调用</th>
                <th className="text-right py-1">Prompt</th>
                <th className="text-right py-1">Completion</th>
                <th className="text-right py-1">总计</th>
              </tr>
            </thead>
            <tbody>
              {ledger.map((row, i) => (
                <tr key={i} style={{ color: 'var(--text-secondary)' }}>
                  <td className="py-0.5">{row.model || 'unknown'}</td>
                  <td className="text-right tabular-nums">{row.calls ?? 0}</td>
                  <td className="text-right tabular-nums">{(row.total_prompt ?? 0).toLocaleString()}</td>
                  <td className="text-right tabular-nums">{(row.total_completion ?? 0).toLocaleString()}</td>
                  <td className="text-right tabular-nums">{(row.total_tokens ?? 0).toLocaleString()}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
