/**
 * settings/ContentPreferencesCard — 内容偏好 (类目 / 来源) 第二轴 (DEV-0315)。
 *
 * A(噪音抑制) + B(显式开关) 整合: 显式声明「这类/这家内容我多要或少要」,
 * 落到 feed 排序第二轴 (与实践域 interest.practice_domains 正交)。
 * 语义: 只改排序、不删除 — 条目永远可达 (不会踩空频道)。
 *
 * 交互: 三级分段控件 (加强/默认/减弱), 点即 PATCH 全量保存 (settings.kv
 * interest.content_preferences + audit_log), 乐观更新 + 失败回滚。
 * 消费方: /api/hotspots 复合排序 (PREF_MULT: more 1.15 / less 0.78)。
 */
import { useCallback, useEffect, useMemo, useState } from 'react';
import { useI18n } from '../../contexts/I18nContext';
import { apiFetch } from '../../lib/api';
import { CATEGORIES } from '../../types';

type Level = 'more' | 'normal' | 'less';
type Axis = 'categories' | 'sources';
type PrefTable = Record<string, Level>;
interface Prefs { categories: PrefTable; sources: PrefTable }

interface ContentPrefsResponse {
  preferences: Partial<Prefs>;
  valid_categories: string[];
  available_sources: { source: string; count: number }[];
  levels: Level[];
}

const LEVELS: Level[] = ['more', 'normal', 'less'];
const VISIBLE_SOURCES = 40;

const labelOfCategory = (id: string) => CATEGORIES.find((c) => c.id === id)?.label ?? id;

/** 三级分段控件: 加强 / 默认 / 减弱 (默认态 = 不存, 等价缺省)。 */
function LevelPicker({
  name, value, onChange, disabled,
}: {
  name: string; value: Level; onChange: (lv: Level) => void; disabled: boolean;
}) {
  const { t } = useI18n();
  return (
    <div
      role="group"
      aria-label={t('settings.content_prefs.level_of', { name })}
      style={{ display: 'inline-flex', alignItems: 'center', gap: 4, flexWrap: 'wrap' }}
    >
      {LEVELS.map((lv) => {
        const active = value === lv;
        const lessActive = active && lv === 'less';
        return (
          <button
            key={lv}
            type="button"
            className={`st-btn${active ? ' primary' : ''}`}
            aria-pressed={active}
            disabled={disabled}
            onClick={() => onChange(lv)}
            style={lessActive
              ? { background: 'var(--sn-cat-sec, #d4574e)', borderColor: 'var(--sn-cat-sec, #d4574e)' }
              : undefined}
          >
            {t(`settings.content_prefs.levels.${lv}`)}
          </button>
        );
      })}
    </div>
  );
}

export function ContentPreferencesCard() {
  const { t } = useI18n();
  const [prefs, setPrefs] = useState<Prefs>({ categories: {}, sources: {} });
  const [validCats, setValidCats] = useState<string[]>([]);
  const [availableSources, setAvailableSources] = useState<{ source: string; count: number }[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(false);
  const [savedFlash, setSavedFlash] = useState(false);
  const [query, setQuery] = useState('');

  useEffect(() => {
    const controller = new AbortController();
    apiFetch<ContentPrefsResponse>('/api/settings/content-preferences', { signal: controller.signal })
      .then((data) => {
        setPrefs({
          categories: data.preferences?.categories || {},
          sources: data.preferences?.sources || {},
        });
        setValidCats(data.valid_categories || []);
        setAvailableSources(data.available_sources || []);
      })
      .catch((e) => { if (e?.name !== 'AbortError') setError(true); })
      .finally(() => setLoading(false));
    return () => controller.abort();
  }, []);

  const setLevel = useCallback((axis: Axis, key: string, level: Level) => {
    if (saving) return;
    const table: PrefTable = { ...(prefs[axis] || {}) };
    if (level === 'normal') delete table[key];
    else table[key] = level;
    const next: Prefs = { ...prefs, [axis]: table };
    setPrefs(next);
    setSaving(true);
    setError(false);
    apiFetch('/api/settings/content-preferences', {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ categories: next.categories, sources: next.sources }),
    })
      .then(() => {
        setSavedFlash(true);
        window.setTimeout(() => setSavedFlash(false), 1500);
      })
      .catch(() => { setPrefs(prefs); setError(true); })  // 回滚到保存前
      .finally(() => setSaving(false));
  }, [prefs, saving]);

  const selectedCount = Object.keys(prefs.categories).length + Object.keys(prefs.sources).length;

  const shownSources = useMemo(() => {
    const q = query.trim().toLowerCase();
    const hit = q ? availableSources.filter((s) => s.source.toLowerCase().includes(q)) : availableSources;
    // 已设置的来源优先置顶 (便于查看/撤销), 其余按量降序 (后端已降序)
    const pinned = hit.filter((s) => prefs.sources[s.source]);
    const rest = hit.filter((s) => !prefs.sources[s.source]);
    return [...pinned, ...rest].slice(0, VISIBLE_SOURCES);
  }, [availableSources, query, prefs.sources]);

  return (
    <section className="st-section" aria-label={t('settings.content_prefs.title')} data-testid="content-prefs-card">
      <h3>{t('settings.content_prefs.title')}</h3>
      <p className="st-section-desc">
        {t('settings.content_prefs.desc')}
        {saving && <span className="st-chip"><i aria-hidden />{t('settings.content_prefs.saving')}</span>}
        {savedFlash && !saving && <span className="st-chip ok"><i aria-hidden />{t('settings.content_prefs.saved')}</span>}
        {error && <span className="st-chip warn"><i aria-hidden />{t('settings.content_prefs.save_failed')}</span>}
      </p>
      <div className="st-section-body">
        {loading ? (
          <p className="st-key">{t('settings.content_prefs.loading')}</p>
        ) : (
          <>
            {/* 类目轴 */}
            <p className="st-key" data-testid="content-prefs-categories">{t('settings.content_prefs.categories')}</p>
            <div data-testid="content-prefs-category-rows">
              {validCats.map((id) => (
                <div key={id} className="flex items-center gap-2" style={{ marginBottom: 6 }} data-testid={`content-prefs-cat-${id}`}>
                  <span className="st-key" style={{ minWidth: 96 }}>{labelOfCategory(id)}</span>
                  <LevelPicker
                    name={labelOfCategory(id)}
                    value={prefs.categories[id] || 'normal'}
                    onChange={(lv) => setLevel('categories', id, lv)}
                    disabled={saving}
                  />
                </div>
              ))}
            </div>

            {/* 来源轴 */}
            <p className="st-key" style={{ marginTop: 12 }} data-testid="content-prefs-sources">{t('settings.content_prefs.sources')}</p>
            <input
              type="search"
              className="st-input"
              placeholder={t('settings.content_prefs.source_placeholder')}
              aria-label={t('settings.content_prefs.source_placeholder')}
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              autoComplete="off"
            />
            {availableSources.length === 0 ? (
              <p className="st-key" style={{ marginTop: 8 }}>{t('settings.content_prefs.sources_empty')}</p>
            ) : (
              <div data-testid="content-prefs-source-rows">
                {shownSources.map((s) => (
                  <div key={s.source} className="flex items-center gap-2" style={{ marginBottom: 6 }} data-testid={`content-prefs-src-${s.source}`}>
                    <span className="st-key" style={{ minWidth: 160 }} title={s.source}>
                      {s.source} <span className="num">{s.count}</span>
                    </span>
                    <LevelPicker
                      name={s.source}
                      value={prefs.sources[s.source] || 'normal'}
                      onChange={(lv) => setLevel('sources', s.source, lv)}
                      disabled={saving}
                    />
                  </div>
                ))}
              </div>
            )}

            <p className="st-key" style={{ marginTop: 10 }} data-testid="content-prefs-note">
              {t('settings.content_prefs.note', { n: selectedCount })}
            </p>
          </>
        )}
      </div>
    </section>
  );
}

export default ContentPreferencesCard;
