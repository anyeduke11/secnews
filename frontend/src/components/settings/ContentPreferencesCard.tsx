/**
 * settings/ContentPreferencesCard — 内容偏好 (DEV-0315 → DEV-0316 AI 自动版)。
 *
 * 三层结构 (优先级: 手动 > LLM 采纳 > 统计自动):
 *  1. 自动学习 (默认生效, 零配置): 系统从你近期赞/踩/浏览/收藏自动推导
 *     类目/来源的加强/减弱 —— 只读展示, 与"点赞即学习"的兴趣引擎同族。
 *  2. AI 优化建议: LLM 看聚合统计给建议 + 理由, 点「采纳」才写入手动层
 *     (与「我的方向」的 AI 推荐域同范式, 建议不自动生效)。
 *  3. 高级手动设置 (默认折叠): 逐类目/来源三级覆盖; 手动项优先于自动,
 *     设回「默认」= 交还给自动学习。
 *
 * 语义: 只升降不删 (条目永远可达); 无信号无手动 = 排序退化原序。
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
  auto_preferences: Partial<Prefs>;
  valid_categories: string[];
  available_sources: { source: string; count: number }[];
  levels: Level[];
}

interface SuggestionsResponse {
  categories: Record<string, 'more' | 'less'>;
  sources: Record<string, 'more' | 'less'>;
  reasons: Record<string, string>;
  cached_at: string | null;
  note: string;
}

const LEVELS: Level[] = ['more', 'normal', 'less'];
const VISIBLE_SOURCES = 40;

const labelOfCategory = (id: string) => CATEGORIES.find((c) => c.id === id)?.label ?? id;

/** 三级分段控件: 加强 / 默认 / 减弱 (默认态 = 不存, 交还自动)。 */
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

/** 自动学习 chips 组 (只读): more=绿 / less=红。 */
function AutoChips({ table }: { table: PrefTable }) {
  const { t } = useI18n();
  return (
    <span className="flex items-center gap-2" style={{ flexWrap: 'wrap', gap: 6 }}>
      {Object.entries(table).map(([key, lv]) => (
        <span
          key={key}
          className="st-chip"
          style={lv === 'less'
            ? { color: 'var(--sn-cat-sec, #d4574e)', borderColor: 'currentColor' }
            : { color: 'var(--sn-mint, #00e5a0)', borderColor: 'currentColor' }}
          title={t('settings.content_prefs.auto_chip_title')}
        >
          <i aria-hidden />{labelOfCategory(key) || key}
          {' · '}{t(`settings.content_prefs.levels.${lv}`)}
        </span>
      ))}
    </span>
  );
}

export function ContentPreferencesCard() {
  const { t } = useI18n();
  const [prefs, setPrefs] = useState<Prefs>({ categories: {}, sources: {} });
  const [autoPrefs, setAutoPrefs] = useState<Partial<Prefs>>({});
  const [validCats, setValidCats] = useState<string[]>([]);
  const [availableSources, setAvailableSources] = useState<{ source: string; count: number }[]>([]);
  const [recs, setRecs] = useState<SuggestionsResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(false);
  const [savedFlash, setSavedFlash] = useState(false);
  const [query, setQuery] = useState('');
  const [advancedOpen, setAdvancedOpen] = useState(false);
  const [recsRefreshing, setRecsRefreshing] = useState(false);

  const loadRecs = useCallback((force: boolean) => {
    if (force) setRecsRefreshing(true);
    apiFetch<SuggestionsResponse>(`/api/interest/content-prefs/recommendations${force ? '?force=1' : ''}`)
      .then(setRecs)
      .catch(() => {})
      .finally(() => { if (force) setRecsRefreshing(false); });
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    apiFetch<ContentPrefsResponse>('/api/settings/content-preferences', { signal: controller.signal })
      .then((data) => {
        setPrefs({
          categories: data.preferences?.categories || {},
          sources: data.preferences?.sources || {},
        });
        setAutoPrefs(data.auto_preferences || {});
        setValidCats(data.valid_categories || []);
        setAvailableSources(data.available_sources || []);
      })
      .catch((e) => { if (e?.name !== 'AbortError') setError(true); })
      .finally(() => setLoading(false));
    loadRecs(false); // 建议失败静默空态 (LLM 不可用不阻塞卡片)
    return () => controller.abort();
  }, [loadRecs]);

  /** 写手动层 (全量 PATCH); 采纳 = 合并进手动层。成功回调刷新自动展示。 */
  const persist = useCallback(
    (next: Prefs, after?: () => void) => {
      setSaving(true);
      setError(false);
      apiFetch<ContentPrefsResponse>('/api/settings/content-preferences', {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ categories: next.categories, sources: next.sources }),
      })
        .then((r) => {
          // PATCH 响应只回 preferences; 重读一次刷新自动/生效展示 (成本小, 保持单一数据路径)
          return apiFetch<ContentPrefsResponse>('/api/settings/content-preferences').then((fresh) => {
            setAutoPrefs(fresh.auto_preferences || {});
            setSavedFlash(true);
            window.setTimeout(() => setSavedFlash(false), 1500);
            after?.();
            void r;
          });
        })
        .catch(() => { setPrefs(prefs); setError(true); })  // 回滚到保存前
        .finally(() => setSaving(false));
    },
    [prefs],
  );

  const setLevel = useCallback((axis: Axis, key: string, level: Level) => {
    if (saving) return;
    const table: PrefTable = { ...(prefs[axis] || {}) };
    if (level === 'normal') delete table[key];
    else table[key] = level;
    const next: Prefs = { ...prefs, [axis]: table };
    setPrefs(next);
    persist(next);
  }, [prefs, saving, persist]);

  /** 采纳一条 AI 建议 → 写入手动层 (人主律: 不自动生效)。 */
  const adopt = useCallback((axis: Axis, key: string, level: 'more' | 'less') => {
    if (saving) return;
    const table: PrefTable = { ...(prefs[axis] || {}), [key]: level };
    const next: Prefs = { ...prefs, [axis]: table };
    setPrefs(next);
    persist(next, () => setRecs((r) => (r ? { ...r, [axis]: Object.fromEntries(Object.entries(r[axis]).filter(([k]) => k !== key)) } : r)));
  }, [prefs, saving, persist]);

  const autoEntries = useMemo(
    () => [
      ...Object.entries(autoPrefs.categories || {}),
      ...Object.entries(autoPrefs.sources || {}),
    ],
    [autoPrefs],
  );
  const pendingRecs = useMemo(() => [
    ...Object.entries(recs?.categories || {}).map(([k, v]) => ({ axis: 'categories' as Axis, key: k, level: v, label: labelOfCategory(k) })),
    ...Object.entries(recs?.sources || {}).map(([k, v]) => ({ axis: 'sources' as Axis, key: k, level: v, label: k })),
  ].filter((r) => prefs[r.axis][r.key] !== r.level), [recs, prefs]);

  const selectedCount = Object.keys(prefs.categories).length + Object.keys(prefs.sources).length;

  const shownSources = useMemo(() => {
    const q = query.trim().toLowerCase();
    const hit = q ? availableSources.filter((s) => s.source.toLowerCase().includes(q)) : availableSources;
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
            {/* ① 自动学习 (零配置, 默认生效) */}
            <div data-testid="content-prefs-auto" style={{ marginBottom: 10 }}>
              <p className="st-key">
                {t('settings.content_prefs.auto_title')}
                <span style={{ marginLeft: 8, opacity: 0.7 }}>{t('settings.content_prefs.auto_desc')}</span>
              </p>
              {autoEntries.length === 0 ? (
                <p className="st-key" style={{ opacity: 0.7 }}>{t('settings.content_prefs.auto_empty')}</p>
              ) : (
                <div className="flex items-center gap-2" style={{ marginTop: 4 }}>
                  {Object.keys(autoPrefs.categories || {}).length > 0 && <AutoChips table={autoPrefs.categories!} />}
                  {Object.keys(autoPrefs.sources || {}).length > 0 && <AutoChips table={autoPrefs.sources!} />}
                </div>
              )}
            </div>

            {/* ② AI 优化建议 (采纳才生效) */}
            <div data-testid="content-prefs-advisor" style={{ marginBottom: 10 }}>
              <p className="st-key" style={{ display: 'inline' }}>{t('settings.content_prefs.advisor_title')}</p>
              <button
                type="button"
                className="st-btn"
                style={{ marginLeft: 8, padding: '1px 8px' }}
                disabled={recsRefreshing}
                onClick={() => loadRecs(true)}
                data-testid="content-prefs-advisor-refresh"
              >
                {t('settings.content_prefs.advisor_refresh')}
              </button>
              {pendingRecs.length === 0 ? (
                <p className="st-key" style={{ opacity: 0.7 }}>{t('settings.content_prefs.advisor_empty')}</p>
              ) : (
                pendingRecs.map((r) => (
                  <div key={`${r.axis}:${r.key}`} className="flex items-center gap-2" style={{ marginBottom: 4 }}>
                    <span
                      className="st-chip"
                      style={r.level === 'less'
                        ? { color: 'var(--sn-cat-sec, #d4574e)', borderColor: 'currentColor' }
                        : { color: 'var(--sn-mint, #00e5a0)', borderColor: 'currentColor' }}
                    >
                      <i aria-hidden />{r.label} · {t(`settings.content_prefs.levels.${r.level}`)}
                    </span>
                    <span className="st-key" style={{ flex: 1 }}>{recs?.reasons[r.key] || ''}</span>
                    <button type="button" className="st-btn" disabled={saving} onClick={() => adopt(r.axis, r.key, r.level)}>
                      {t('settings.content_prefs.adopt')}
                    </button>
                  </div>
                ))
              )}
            </div>

            {/* ③ 高级手动设置 (默认折叠; 手动优先于自动) */}
            <button
              type="button"
              className="st-btn ghost"
              aria-expanded={advancedOpen}
              onClick={() => setAdvancedOpen((o) => !o)}
              data-testid="content-prefs-advanced-toggle"
            >
              {advancedOpen ? '▾' : '▸'} {t('settings.content_prefs.advanced')}
              {selectedCount > 0 && <span className="st-chip" style={{ marginLeft: 6 }}>{selectedCount}</span>}
            </button>
            {advancedOpen && (
              <div data-testid="content-prefs-advanced" style={{ marginTop: 8 }}>
                <p className="st-key" style={{ opacity: 0.7, marginBottom: 8 }}>{t('settings.content_prefs.advanced_hint')}</p>
                <p className="st-key">{t('settings.content_prefs.categories')}</p>
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
                      {autoPrefs.categories?.[id] && !prefs.categories[id] && (
                        <span className="st-key" style={{ opacity: 0.6 }} title={t('settings.content_prefs.auto_chip_title')}>
                          {t('settings.content_prefs.auto_badge')} {t(`settings.content_prefs.levels.${autoPrefs.categories[id]}`)}
                        </span>
                      )}
                    </div>
                  ))}
                </div>

                <p className="st-key" style={{ marginTop: 12 }}>{t('settings.content_prefs.sources')}</p>
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
                        {autoPrefs.sources?.[s.source] && !prefs.sources[s.source] && (
                          <span className="st-key" style={{ opacity: 0.6 }} title={t('settings.content_prefs.auto_chip_title')}>
                            {t('settings.content_prefs.auto_badge')} {t(`settings.content_prefs.levels.${autoPrefs.sources[s.source]}`)}
                          </span>
                        )}
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )}
          </>
        )}
      </div>
    </section>
  );
}

export default ContentPreferencesCard;
