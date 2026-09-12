/**
 * settings/PracticeDomainsCard — 实践域兴趣画像 + 行为权重 (Workbench Focus P0.3/R1, DEV-0182)
 *
 * 勾选安全从业者的实践方向 (10 域, 与 auto_classifier 词表同源);
 * 点击即 PATCH 全量保存 (settings.kv interest.practice_domains + audit_log)。
 * R1 升级: 权重条展示行为分 (interest/weights), 重置按钮清行为信号。
 * 消费方: /api/hotspots 排序乘子 (降权不删) 与 SK-01 每日优先级摘要分区。
 * 空画像 + 无行为 = 不过滤 (资讯流保持无偏好默认行为)。
 */
import { useCallback, useEffect, useState } from 'react';
import { useI18n } from '../../contexts/I18nContext';
import { apiFetch } from '../../lib/api';

interface InterestsResponse {
  domains: string[];
  valid_domains: string[];
  labels: Record<string, string>;
}

interface WeightEntry {
  explicit_selected: number;
  behavioral_score: number;
  blended_score: number;
  events_30d: number;
  last_event_at: string | null;
}

interface WeightsResponse {
  weights: Record<string, WeightEntry>;
  domains: string[];
}

export function PracticeDomainsCard() {
  const { t } = useI18n();
  const [domains, setDomains] = useState<string[]>([]);
  const [options, setOptions] = useState<{ id: string; label: string }[]>([]);
  const [weights, setWeights] = useState<Record<string, WeightEntry>>({});
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(false);
  const [savedFlash, setSavedFlash] = useState(false);

  const loadWeights = useCallback(() => {
    apiFetch<WeightsResponse>('/api/interest/weights')
      .then((w) => setWeights(w.weights || {}))
      .catch(() => {});
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    apiFetch<InterestsResponse>('/api/settings/interests', { signal: controller.signal })
      .then((data) => {
        setDomains(data.domains || []);
        setOptions((data.valid_domains || []).map((id) => ({ id, label: data.labels?.[id] || id })));
      })
      .catch((e) => {
        if (e?.name !== 'AbortError') setError(true);
      })
      .finally(() => setLoading(false));
    loadWeights();
    return () => controller.abort();
  }, [loadWeights]);

  const toggle = useCallback(
    (id: string) => {
      if (saving) return;
      const next = domains.includes(id) ? domains.filter((d) => d !== id) : [...domains, id];
      setDomains(next);
      setSaving(true);
      setError(false);
      apiFetch<{ status: string }>('/api/settings/interests', {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ domains: next }),
      })
        .then(() => {
          setSavedFlash(true);
          window.setTimeout(() => setSavedFlash(false), 1500);
          loadWeights(); // 勾选变更影响 S(d), 刷新权重条
        })
        .catch(() => {
          setDomains(domains); // 回滚到保存前
          setError(true);
        })
        .finally(() => setSaving(false));
    },
    [domains, saving, loadWeights],
  );

  const resetBehavior = useCallback(() => {
    if (saving) return;
    setSaving(true);
    apiFetch('/api/interest/reset', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}' })
      .then(() => loadWeights())
      .catch(() => setError(true))
      .finally(() => setSaving(false));
  }, [saving, loadWeights]);

  const hasBehavior = Object.values(weights).some((w) => w.events_30d > 0);

  return (
    <section className="st-section" aria-label={t('settings.practice_domains.section_aria')} data-testid="practice-domains-card">
      <h3>{t('settings.practice_domains.title')}</h3>
      <p className="st-section-desc">
        {t('settings.practice_domains.desc')}
        {saving && <span className="st-chip"><i aria-hidden />{t('settings.practice_domains.saving')}</span>}
        {savedFlash && !saving && <span className="st-chip ok"><i aria-hidden />{t('settings.practice_domains.saved')}</span>}
        {error && <span className="st-chip warn"><i aria-hidden />{t('settings.practice_domains.save_failed')}</span>}
      </p>
      <div className="st-section-body">
        {loading ? (
          <p className="st-key">{t('settings.practice_domains.loading')}</p>
        ) : (
          <div className="st-ctrlrow flex-wrap" role="group" aria-label={t('settings.practice_domains.group_aria')}>
            {options.map((opt) => {
              const active = domains.includes(opt.id);
              return (
                <button
                  key={opt.id}
                  type="button"
                  className={active ? 'st-btn primary' : 'st-btn'}
                  aria-pressed={active}
                  disabled={saving}
                  onClick={() => toggle(opt.id)}
                >
                  {opt.label}
                </button>
              );
            })}
          </div>
        )}
        {!loading && domains.length === 0 && (
          <p className="st-key" style={{ marginTop: 8 }}>{t('settings.practice_domains.empty')}</p>
        )}
        {/* R1 权重条: 行为贡献可视化 (可解释性闭环) */}
        {hasBehavior && (
          <div style={{ marginTop: 10 }} data-testid="interest-weight-bars">
            {Object.entries(weights)
              .filter(([, w]) => w.events_30d > 0 || w.explicit_selected)
              .sort((a, b) => b[1].blended_score - a[1].blended_score)
              .map(([id, w]) => (
                <div key={id} className="flex items-center gap-2" style={{ marginBottom: 4 }}>
                  <span className="st-key" style={{ minWidth: 90 }}>{options.find((o) => o.id === id)?.label || id}</span>
                  <div
                    aria-hidden
                    style={{
                      flex: 1, height: 6, borderRadius: 3,
                      backgroundColor: 'var(--border-subtle, rgba(128,128,128,0.2))',
                      overflow: 'hidden',
                    }}
                  >
                    <div style={{
                      width: `${Math.round(w.blended_score * 100)}%`, height: '100%',
                      backgroundColor: 'var(--accent, #00bcd4)',
                    }} />
                  </div>
                  <span className="st-key" style={{ minWidth: 60, textAlign: 'right' }}>
                    {t('settings.practice_domains.events_30d', { n: w.events_30d })}
                  </span>
                </div>
              ))}
            <button
              type="button"
              className="st-btn"
              style={{ marginTop: 6 }}
              disabled={saving}
              onClick={resetBehavior}
            >
              {t('settings.practice_domains.reset_behavior')}
            </button>
          </div>
        )}
      </div>
    </section>
  );
}
