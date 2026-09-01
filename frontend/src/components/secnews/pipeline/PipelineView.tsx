/**
 * PipelineView — 管线观测台
 *
 * 展示 KL 管线五阶段漏斗 + 书签存活三态 + 队列/死信表 + token 台账。
 * v0.7 Batch ⑨ B9-1: 接入 i18n (pipeline.* namespace)
 */
import { useState, useEffect } from 'react';
import { SecNewsHeader } from '../layout/SecNewsHeader';
import { AliveCard } from './AliveCard';
import { FunnelBar } from './FunnelBar';
import { QueueCard } from './QueueCard';
import { TokenLedger } from './TokenLedger';
import { useI18n } from '../../../contexts/I18nContext';

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
  const { t } = useI18n();
  const [stats, setStats] = useState<PipelineStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchStats = async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch('/api/secnews/pipeline');
      if (!res.ok) {
        setError(`${t('pipeline.data_load_failed')} (${res.status})`);
        return;
      }
      setStats(await res.json());
    } catch {
      setError(t('pipeline.data_load_failed_network'));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { fetchStats(); /* eslint-disable-next-line react-hooks/exhaustive-deps */ }, []);
  useEffect(() => {
    const timer = window.setInterval(fetchStats, 30_000);
    return () => window.clearInterval(timer);
  }, []);

  if (loading && !stats) {
    return <div className="text-sm py-8 text-center" style={{ color: 'var(--text-muted)' }} role="status" aria-live="polite">{t('pipeline.loading')}</div>;
  }

  return (
    <div>
      <SecNewsHeader title={t('pipeline.title')} onRefresh={fetchStats} refreshing={loading} />
      {error && !loading && !stats && (
        <div className="py-8 text-center">
          <p className="text-sm" style={{ color: 'var(--color-error)' }} role="alert">{error}</p>
        </div>
      )}
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
