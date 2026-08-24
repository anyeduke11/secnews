/**
 * PipelineView — 管线观测台
 *
 * 展示 KL 管线五阶段漏斗 + 书签存活三态 + 队列/死信表 + token 台账。
 */
import { useState, useEffect } from 'react';
import { SecNewsHeader } from '../layout/SecNewsHeader';
import { AliveCard } from './AliveCard';
import { FunnelBar } from './FunnelBar';
import { QueueCard } from './QueueCard';
import { TokenLedger } from './TokenLedger';

interface PipelineStats {
  funnel: Array<{ stage: string; count: number }>;
  queue: { pending: number; running: number; error: number };
  errors: Array<{
    id: number;
    item_id: string;
    stage: string;
    attempts: number;
    last_error: string;
    updated_at: string;
  }>;
  alive: { total: number; alive: number; dead: number; unknown: number };
  ledger: Array<{ model: string; calls: number; total_tokens: number }>;
}

export function PipelineView() {
  const [stats, setStats] = useState<PipelineStats | null>(null);
  const [loading, setLoading] = useState(true);

  const fetchStats = async () => {
    setLoading(true);
    try {
      const res = await fetch('/api/secnews/pipeline');
      const data = await res.json();
      setStats(data);
    } catch {
      setStats(null);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { fetchStats(); }, []);

  if (loading && !stats) {
    return <div className="text-sm py-8 text-center" style={{ color: 'var(--text-muted)' }}>加载中...</div>;
  }

  return (
    <div>
      <SecNewsHeader title="管线观测" onRefresh={fetchStats} refreshing={loading} />
      {stats && (
        <div className="flex flex-col gap-4">
          <FunnelBar funnel={stats.funnel} />
          <AliveCard alive={stats.alive} onSwept={fetchStats} />
          <QueueCard queue={stats.queue} errors={stats.errors} />
          <TokenLedger />
        </div>
      )}
    </div>
  );
}
