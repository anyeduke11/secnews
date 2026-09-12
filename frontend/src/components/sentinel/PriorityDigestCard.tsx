/**
 * PriorityDigestCard — SK-01 今日重点情报卡 (Workbench Focus T0.5 收敛, DEV-0177)
 *
 * 数据源: GET /api/digests/priority (后端 5min TTL 缓存, 优雅降级)。
 * 渲染: 有画像 → 按兴趣域分组 (命中域在前, 其余归「其他」); 无画像 → 单列表单。
 * 只读展示, 不再回触生成。样式走内联 + CSS 变量 (与 DigestCard 同风格)。
 */
import { useCallback, useEffect, useState } from 'react';
import { useI18n } from '../../contexts/I18nContext';
import { PRACTICE_DOMAIN_LABELS } from '../../types';
import { apiFetch } from '../../lib/api';

interface PriorityItem {
  title?: string;
  practice_domain?: string | null;
  [key: string]: unknown;
}

interface PriorityResponse {
  top_items: PriorityItem[];
  suggested_actions: string[];
  mode: string;
  interest_domains: string[];
  practice_partitions: Record<string, PriorityItem[]> | null;
  cached?: boolean;
}

export function PriorityDigestCard() {
  const { t } = useI18n();
  const [data, setData] = useState<PriorityResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);

  const load = useCallback((force = false) => {
    setLoading(true);
    setError(false);
    apiFetch<PriorityResponse>(`/api/digests/priority${force ? '?force=true' : ''}`)
      .then(setData)
      .catch(() => setError(true))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => { load(); }, [load]);

  const items = data?.top_items || [];
  const partitions = data?.practice_partitions || null;
  const interestOrder = data?.interest_domains || [];

  // 分组顺序: interest_domains 顺序 → other; 无画像 → 单组
  const groups: { key: string; label: string | null; items: PriorityItem[] }[] = [];
  if (partitions) {
    for (const d of interestOrder) {
      const list = partitions[d];
      if (list?.length) groups.push({ key: d, label: PRACTICE_DOMAIN_LABELS[d] || d, items: list });
    }
    if (partitions.other?.length) groups.push({ key: 'other', label: t('feed.priority.other'), items: partitions.other });
  } else if (items.length) {
    groups.push({ key: 'all', label: null, items });
  }

  return (
    <section
      aria-label={t('feed.priority.title')}
      data-testid="priority-digest"
      className="p-3 rounded-[var(--radius-sm)]"
      style={{
        backgroundColor: 'var(--bg-elevated)',
        border: '1px solid var(--border-color)',
        borderLeft: '3px solid var(--accent)',
      }}
    >
      <div className="flex items-center justify-between mb-1.5">
        <h3 className="text-xs font-mono font-semibold" style={{ color: 'var(--text-primary)' }}>
          {t('feed.priority.title')}
        </h3>
        <button
          type="button"
          onClick={() => load(true)}
          disabled={loading}
          className="text-[10px] px-2 py-0.5 rounded"
          style={{ border: '1px solid var(--border-color)', color: 'var(--text-muted)' }}
        >
          {loading ? t('feed.priority.loading') : t('feed.priority.refresh')}
        </button>
      </div>

      {error && (
        <p className="text-[10px] font-mono" style={{ color: 'var(--color-error)' }} role="alert">
          {t('feed.priority.error')}
        </p>
      )}

      {!error && groups.length === 0 && (
        <p className="text-[10px] font-mono" style={{ color: 'var(--text-muted)' }}>
          {loading ? t('feed.priority.loading') : t('feed.priority.empty')}
        </p>
      )}

      <div className="space-y-2">
        {groups.map(g => (
          <div key={g.key}>
            {g.label && (
              <div className="text-[10px] font-mono uppercase tracking-widest mb-0.5" style={{ color: 'var(--accent)' }} data-domain={g.key}>
                {g.label}
              </div>
            )}
            <ul className="space-y-0.5">
              {g.items.map((it, i) => (
                <li key={`${g.key}-${i}`} className="text-[11px] leading-snug" style={{ color: 'var(--text-secondary)' }}>
                  · {it.title || String(it.summary || '')}
                </li>
              ))}
            </ul>
          </div>
        ))}
      </div>
    </section>
  );
}
