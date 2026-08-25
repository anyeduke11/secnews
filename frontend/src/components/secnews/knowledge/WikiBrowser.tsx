/**
 * WikiBrowser — Wiki 知识库浏览视图
 *
 * 展示知识库条目统计 + 生命周期分布 + Inbox 扫描入库 (S1-5)。
 */
import { useState, useEffect, useCallback } from 'react';
import { SecNewsHeader } from '../layout/SecNewsHeader';
import { InboxScanner } from './InboxScanner';

interface KnowledgeStats {
  items: number;
  concepts: number;
  stage_distribution: Record<string, number>;
}

export function WikiBrowser() {
  const [stats, setStats] = useState<KnowledgeStats | null>(null);
  const [loading, setLoading] = useState(true);

  const fetchStats = useCallback(async () => {
    setLoading(true);
    try {
      const res = await fetch('/api/secnews/knowledge');
      const data = await res.json();
      setStats(data);
    } catch {
      setStats(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { fetchStats(); }, [fetchStats]);

  return (
    <div>
      <SecNewsHeader title="知识库" onRefresh={fetchStats} refreshing={loading} />
      {loading && !stats && (
        <div className="text-sm py-8 text-center" style={{ color: 'var(--text-muted)' }}>加载中...</div>
      )}
      {stats && (
        <div className="flex flex-col gap-4">
          {/* S1-5: Inbox 扫描 + quarantine 隔离区 */}
          <InboxScanner onScanned={fetchStats} />
          <div className="grid grid-cols-2 gap-3">
            <div className="p-3 rounded-[var(--radius-sm)]" style={{ border: '1px solid var(--border-color)' }}>
              <div className="text-[10px] font-mono" style={{ color: 'var(--text-muted)' }}>知识条目</div>
              <div className="text-lg font-mono font-semibold mt-1" style={{ color: 'var(--text-primary)' }}>
                {stats.items.toLocaleString()}
              </div>
            </div>
            <div className="p-3 rounded-[var(--radius-sm)]" style={{ border: '1px solid var(--border-color)' }}>
              <div className="text-[10px] font-mono" style={{ color: 'var(--text-muted)' }}>概念卡</div>
              <div className="text-lg font-mono font-semibold mt-1" style={{ color: 'var(--text-primary)' }}>
                {stats.concepts.toLocaleString()}
              </div>
            </div>
          </div>
          <div className="p-3 rounded-[var(--radius-sm)]" style={{ border: '1px solid var(--border-color)' }}>
            <h3 className="text-xs font-mono font-medium mb-2" style={{ color: 'var(--text-primary)' }}>生命周期分布</h3>
            {Object.entries(stats.stage_distribution).map(([stage, count]) => (
              <div key={stage} className="flex items-center justify-between py-0.5">
                <span className="text-[10px] font-mono" style={{ color: 'var(--text-muted)' }}>{stage}</span>
                <span className="text-[10px] font-mono tabular-nums" style={{ color: 'var(--text-secondary)' }}>
                  {(count as number).toLocaleString()}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
