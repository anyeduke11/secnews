/**
 * InfoFilterCard — 独立资讯筛选门禁控制面板 (v0.8 P1, Sentinel V2 token)
 *
 * 一键启停 (受管门禁, feature gate) + 规则 CRUD + 实时命中预览
 * 数据源: GET /api/info-filter/rules · /gate · POST /rules · PATCH /rules/{id}
 *         DELETE /rules/{id} · POST /preview
 *
 * 行为:
 * - gate off → 显示禁用提示卡 (与 dsh 同模式)
 * - gate on → 显示规则列表 + 新增/编辑/启停/删除 + 实时预览
 * - V2: 全部走 settings-shell.css 的 st-cellgrid / st-section / st-rule / st-chip
 */
import { useCallback, useEffect, useState } from 'react';
import { useI18n } from '../../../contexts/I18nContext';

interface FilterRule {
  id: number;
  rule_type: 'allow' | 'deny';
  match_kind: 'category' | 'source_name' | 'source_id' | 'tag';
  match_value: string;
  enabled: number;
  note: string;
  created_at: string;
  updated_at: string;
}

interface PreviewResult {
  verdict: 'allow' | 'deny' | 'neutral';
  matched_rule: FilterRule | null;
}

interface GateStatus {
  extension: string;
  is_enabled: boolean;
}

const MATCH_KINDS = ['source_name', 'source_id', 'category', 'tag'] as const;

export function InfoFilterCard() {
  const { t } = useI18n();
  const [gateOff, setGateOff] = useState(false);
  const [rules, setRules] = useState<FilterRule[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [opMsg, setOpMsg] = useState<{ kind: 'ok' | 'err'; text: string } | null>(null);

  // 新增表单
  const [newRuleType, setNewRuleType] = useState<'deny' | 'allow'>('deny');
  const [newMatchKind, setNewMatchKind] = useState<typeof MATCH_KINDS[number]>('source_name');
  const [newMatchValue, setNewMatchValue] = useState('');
  const [newNote, setNewNote] = useState('');

  // 预览
  const [previewCat, setPreviewCat] = useState('tech');
  const [previewName, setPreviewName] = useState('华尔街见闻');
  const [previewResult, setPreviewResult] = useState<PreviewResult | null>(null);

  const refresh = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const gateR = await fetch('/api/info-filter/gate');
      if (gateR.status === 404) {
        setGateOff(true);
        return;
      }
      if (!gateR.ok) {
        setError(t('info_filter.gate_load_failed'));
        return;
      }
      const gate: GateStatus = await gateR.json();
      if (!gate.is_enabled) {
        setGateOff(true);
        return;
      }
      setGateOff(false);
      const rulesR = await fetch('/api/info-filter/rules');
      if (!rulesR.ok) {
        setError(t('info_filter.rules_load_failed'));
        return;
      }
      const d = await rulesR.json();
      setRules(d.rules || []);
    } catch {
      setError(t('info_filter.network_error'));
    } finally {
      setLoading(false);
    }
  }, [t]);

  useEffect(() => { refresh(); }, [refresh]);

  const createRule = async () => {
    if (!newMatchValue.trim()) {
      setOpMsg({ kind: 'err', text: t('info_filter.value_required') });
      return;
    }
    setOpMsg(null);
    try {
      const r = await fetch('/api/info-filter/rules', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          rule_type: newRuleType,
          match_kind: newMatchKind,
          match_value: newMatchValue.trim(),
          note: newNote,
        }),
      });
      if (!r.ok) {
        const d = await r.json().catch(() => ({}));
        setOpMsg({ kind: 'err', text: `${t('info_filter.create_failed')}: ${d.detail ?? r.status}` });
        return;
      }
      setOpMsg({ kind: 'ok', text: t('info_filter.created') });
      setNewMatchValue('');
      setNewNote('');
      await refresh();
    } catch {
      setOpMsg({ kind: 'err', text: t('info_filter.network_error') });
    }
  };

  const toggleRule = async (rule: FilterRule) => {
    try {
      await fetch(`/api/info-filter/rules/${rule.id}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ enabled: rule.enabled ? 0 : 1 }),
      });
      await refresh();
    } catch {
      setOpMsg({ kind: 'err', text: t('info_filter.network_error') });
    }
  };

  const deleteRule = async (id: number) => {
    if (!window.confirm(t('info_filter.delete_confirm'))) return;
    try {
      await fetch(`/api/info-filter/rules/${id}`, { method: 'DELETE' });
      setOpMsg({ kind: 'ok', text: t('info_filter.deleted') });
      await refresh();
    } catch {
      setOpMsg({ kind: 'err', text: t('info_filter.network_error') });
    }
  };

  const runPreview = async () => {
    if (!previewName.trim()) return;
    try {
      const r = await fetch('/api/info-filter/preview', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          category: previewCat.trim(),
          source_name: previewName.trim(),
        }),
      });
      if (r.ok) {
        const d = await r.json();
        setPreviewResult(d);
      }
    } catch {
      setOpMsg({ kind: 'err', text: t('info_filter.network_error') });
    }
  };

  if (gateOff) {
    return (
      <div className="space-y-3" data-testid="info-filter-card">
        <section className="st-section" aria-label={t('info_filter.title')}>
          <h3>{t('info_filter.title')}</h3>
          <p className="st-section-desc">{t('info_filter.disabled_hint')}</p>
          <p className="st-section-desc">{t('info_filter.fallback_pass')}</p>
        </section>
      </div>
    );
  }

  return (
    <div className="space-y-3" data-testid="info-filter-card">
      <div className="st-actionbar" style={{ borderTop: 'none', marginTop: 0, paddingTop: 0 }}>
        {error && !loading && <span className="st-ab-msg bad">{error}</span>}
        {opMsg && <span className={`st-ab-msg ${opMsg.kind}`}>{opMsg.text}</span>}
        <button type="button" className="st-btn ghost" onClick={refresh} disabled={loading}
                aria-label={t('info_filter.refresh')}>
          {loading ? t('info_filter.refreshing') : t('info_filter.refresh')}
        </button>
      </div>

      <section className="st-section" aria-label={t('info_filter.title')}>
        <h3>{t('info_filter.title')}</h3>
        <p className="st-section-desc">{t('info_filter.desc')}</p>
        <div className="st-section-body">
          {/* 现状 */}
          <div className="st-cellgrid">
            <div className="st-cell">
              <span className="st-cellk">{t('info_filter.rules_count')}</span>
              <span className="st-cellv sm">{rules.length}</span>
            </div>
            <div className="st-cell">
              <span className="st-cellk">{t('info_filter.enabled_count')}</span>
              <span className="st-cellv sm mint">
                {rules.filter(r => r.enabled).length}
              </span>
            </div>
          </div>

          {/* 新增规则 */}
          <div className="st-rule" />
          <h4 style={{
            fontFamily: 'var(--sn-mono)',
            fontSize: 'var(--sn-fs-h4)',
            color: 'var(--sn-ink)',
            margin: '12px 0 8px',
          }}>{t('info_filter.add_rule')}</h4>
          <div className="st-cellgrid">
            <label className="st-cell">
              <span className="st-cellk">{t('info_filter.rule_type')}</span>
              <select
                className="st-input"
                value={newRuleType}
                onChange={e => setNewRuleType(e.target.value as 'deny' | 'allow')}
                aria-label={t('info_filter.rule_type')}
              >
                <option value="deny">deny</option>
                <option value="allow">allow</option>
              </select>
            </label>
            <label className="st-cell">
              <span className="st-cellk">{t('info_filter.match_kind')}</span>
              <select
                className="st-input"
                value={newMatchKind}
                onChange={e => setNewMatchKind(e.target.value as typeof MATCH_KINDS[number])}
                aria-label={t('info_filter.match_kind')}
              >
                {MATCH_KINDS.map(k => (
                  <option key={k} value={k}>{k}</option>
                ))}
              </select>
            </label>
            <label className="st-cell" style={{ gridColumn: 'span 2' }}>
              <span className="st-cellk">{t('info_filter.match_value')}</span>
              <input
                className="st-input"
                type="text"
                value={newMatchValue}
                onChange={e => setNewMatchValue(e.target.value)}
                placeholder={t('info_filter.match_value_placeholder')}
                aria-label={t('info_filter.match_value')}
              />
            </label>
            <label className="st-cell" style={{ gridColumn: 'span 2' }}>
              <span className="st-cellk">{t('info_filter.note')}</span>
              <input
                className="st-input"
                type="text"
                value={newNote}
                onChange={e => setNewNote(e.target.value)}
                placeholder={t('info_filter.note_placeholder')}
                aria-label={t('info_filter.note')}
              />
            </label>
          </div>
          <button
            type="button"
            className="st-btn primary"
            onClick={createRule}
            disabled={!newMatchValue.trim()}
            style={{ marginTop: 10 }}
          >
            {t('info_filter.add')}
          </button>
        </div>
      </section>

      {/* 规则列表 */}
      <section className="st-section" aria-label={t('info_filter.rules_list')}>
        <h3>{t('info_filter.rules_list')}</h3>
        <div className="st-section-body">
          {!loading && rules.length === 0 && (
            <div className="st-info">{t('info_filter.no_rules')}</div>
          )}
          {rules.map(r => (
            <div key={r.id} className="st-card" style={{ marginBottom: 8 }}>
              <div className="flex items-center gap-2 flex-wrap">
                <span className={`st-chip ${r.rule_type === 'deny' ? 'bad' : 'ok'}`}>
                  {r.rule_type}
                </span>
                <span className="st-chip">{r.match_kind}</span>
                <code style={{ fontFamily: 'var(--sn-mono)', color: 'var(--sn-ink)' }}>
                  {r.match_value}
                </code>
                {r.note && (
                  <span style={{
                    fontFamily: 'var(--sn-mono)',
                    fontSize: 'var(--sn-fs-mute)',
                    color: 'var(--sn-ink-3)',
                  }}>
                    — {r.note}
                  </span>
                )}
                <div className="ml-auto flex gap-1">
                  <button
                    type="button"
                    className="st-btn ghost xs"
                    onClick={() => toggleRule(r)}
                  >
                    {r.enabled ? t('info_filter.disable') : t('info_filter.enable')}
                  </button>
                  <button
                    type="button"
                    className="st-btn ghost xs"
                    onClick={() => deleteRule(r.id)}
                  >
                    {t('info_filter.delete')}
                  </button>
                </div>
              </div>
            </div>
          ))}
        </div>
      </section>

      {/* 实时预览 */}
      <section className="st-section" aria-label={t('info_filter.preview')}>
        <h3>{t('info_filter.preview')}</h3>
        <p className="st-section-desc">{t('info_filter.preview_desc')}</p>
        <div className="st-section-body">
          <div className="st-cellgrid">
            <label className="st-cell">
              <span className="st-cellk">{t('info_filter.preview_category')}</span>
              <input
                className="st-input"
                type="text"
                value={previewCat}
                onChange={e => setPreviewCat(e.target.value)}
                aria-label={t('info_filter.preview_category')}
              />
            </label>
            <label className="st-cell">
              <span className="st-cellk">{t('info_filter.preview_source')}</span>
              <input
                className="st-input"
                type="text"
                value={previewName}
                onChange={e => setPreviewName(e.target.value)}
                aria-label={t('info_filter.preview_source')}
              />
            </label>
          </div>
          <button
            type="button"
            className="st-btn primary"
            onClick={runPreview}
            disabled={!previewName.trim()}
            style={{ marginTop: 10 }}
          >
            {t('info_filter.preview_run')}
          </button>
          {previewResult && (
            <div style={{ marginTop: 12 }}>
              <span className={`st-chip ${
                previewResult.verdict === 'deny' ? 'bad'
                  : previewResult.verdict === 'allow' ? 'ok' : 'mute'
              }`}>
                {t('info_filter.verdict')}: {previewResult.verdict}
              </span>
              {previewResult.matched_rule && (
                <span style={{
                  marginLeft: 8,
                  fontFamily: 'var(--sn-mono)',
                  fontSize: 'var(--sn-fs-mute)',
                  color: 'var(--sn-ink-3)',
                }}>
                  {previewResult.matched_rule.rule_type}/
                  {previewResult.matched_rule.match_kind}/
                  {previewResult.matched_rule.match_value}
                </span>
              )}
            </div>
          )}
        </div>
      </section>
    </div>
  );
}
