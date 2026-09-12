/**
 * settings/PracticeDomainsCard — 实践域兴趣画像 (Workbench Focus PRD P0.3, DEV-0176)
 *
 * 勾选安全从业者的实践方向 (8 域, 与 auto_classifier 词表同源);
 * 点击即 PATCH 全量保存 (settings.kv interest.practice_domains + audit_log)。
 * 消费方: /api/hotspots 排序加权 (降权不删) 与 SK-01 每日优先级摘要分区。
 * 空画像 = 不过滤 (资讯流保持无偏好默认行为)。
 * i18n: 静态文案走 useI18n; 域标签为后端 labels 数据 (非 i18n key)。
 */
import { useCallback, useEffect, useState } from 'react';
import { useI18n } from '../../contexts/I18nContext';
import { apiFetch } from '../../lib/api';

interface InterestsResponse {
  domains: string[];
  valid_domains: string[];
  labels: Record<string, string>;
}

export function PracticeDomainsCard() {
  const { t } = useI18n();
  const [domains, setDomains] = useState<string[]>([]);
  const [options, setOptions] = useState<{ id: string; label: string }[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(false);
  const [savedFlash, setSavedFlash] = useState(false);

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
    return () => controller.abort();
  }, []);

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
        })
        .catch(() => {
          setDomains(domains); // 回滚到保存前
          setError(true);
        })
        .finally(() => setSaving(false));
    },
    [domains, saving],
  );

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
      </div>
    </section>
  );
}
