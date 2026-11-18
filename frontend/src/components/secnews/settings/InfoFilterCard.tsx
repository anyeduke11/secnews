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
 *
 * 拆分 (前端重构 V1 B6-b, 单文件 ≤300 行): 三个展示区块移至同目录
 * InfoFilterAddForm / InfoFilterRuleList / InfoFilterPreview, 共享类型在 infoFilter.types。
 * 状态与请求逻辑全部保留在本组件, 区块仅为受控视图 (零行为/DOM 变更)。
 */
import { useCallback, useEffect, useState } from 'react';
import { useI18n } from '../../../contexts/I18nContext';
import { ApiError } from '../../../lib/api';
import {
  createInfoFilterRule,
  deleteInfoFilterRule,
  getInfoFilterGate,
  listInfoFilterRules,
  patchInfoFilterRule,
  previewInfoFilter,
} from '../../../api/secnews';
import type { FilterRule, GateStatus, PreviewResult } from '../../../api/secnews';
import { useAbortGuard } from '../../../hooks/useAbortGuard';
import { InfoFilterAddForm } from './InfoFilterAddForm';
import { InfoFilterRuleList } from './InfoFilterRuleList';
import { InfoFilterPreview } from './InfoFilterPreview';
import type { MatchKind, RuleType } from './infoFilter.types';

export function InfoFilterCard() {
  const { t } = useI18n();
  const [gateOff, setGateOff] = useState(false);
  const [rules, setRules] = useState<FilterRule[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [opMsg, setOpMsg] = useState<{ kind: 'ok' | 'err'; text: string } | null>(null);

  // 新增表单
  const [newRuleType, setNewRuleType] = useState<RuleType>('deny');
  const [newMatchKind, setNewMatchKind] = useState<MatchKind>('source_name');
  const [newMatchValue, setNewMatchValue] = useState('');
  const [newNote, setNewNote] = useState('');

  // 预览
  const [previewCat, setPreviewCat] = useState('tech');
  const [previewName, setPreviewName] = useState('华尔街见闻');
  const [previewResult, setPreviewResult] = useState<PreviewResult | null>(null);
  const dead = useAbortGuard(); // P1-7 竞态守卫: 卸载后不写状态

  const refresh = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      let gate: GateStatus;
      try {
        gate = await getInfoFilterGate();
      } catch (e) {
        if (dead.current) return;
        // 404 = feature gate 关闭 (原 r.status === 404 分支)
        if (e instanceof ApiError && e.status === 404) {
          setGateOff(true);
          return;
        }
        setError(e instanceof ApiError ? t('info_filter.gate_load_failed') : t('info_filter.network_error'));
        return;
      }
      if (dead.current) return;
      if (!gate.is_enabled) {
        setGateOff(true);
        return;
      }
      setGateOff(false);
      try {
        const d = await listInfoFilterRules();
        if (dead.current) return;
        setRules(d.rules || []);
      } catch {
        if (dead.current) return;
        setError(t('info_filter.rules_load_failed'));
      }
    } finally {
      if (!dead.current) setLoading(false);
    }
  }, [t, dead]);

  useEffect(() => { refresh(); }, [refresh]);

  const createRule = async () => {
    if (!newMatchValue.trim()) {
      setOpMsg({ kind: 'err', text: t('info_filter.value_required') });
      return;
    }
    setOpMsg(null);
    try {
      // 非 2xx 由 apiFetch 抛 ApiError (message 经 getApiErrorMessage/{error} 兜底)
      await createInfoFilterRule({
        rule_type: newRuleType,
        match_kind: newMatchKind,
        match_value: newMatchValue.trim(),
        note: newNote,
      });
      if (dead.current) return;
      setOpMsg({ kind: 'ok', text: t('info_filter.created') });
      setNewMatchValue('');
      setNewNote('');
      await refresh();
    } catch (e) {
      if (dead.current) return;
      setOpMsg({
        kind: 'err',
        text: e instanceof ApiError
          ? `${t('info_filter.create_failed')}: ${e.message}`
          : t('info_filter.network_error'),
      });
    }
  };

  const toggleRule = async (rule: FilterRule) => {
    try {
      await patchInfoFilterRule(rule.id, { enabled: rule.enabled ? 0 : 1 });
      await refresh();
    } catch {
      if (dead.current) return;
      setOpMsg({ kind: 'err', text: t('info_filter.network_error') });
    }
  };

  const deleteRule = async (id: number) => {
    if (!window.confirm(t('info_filter.delete_confirm'))) return;
    try {
      await deleteInfoFilterRule(id);
      if (dead.current) return;
      setOpMsg({ kind: 'ok', text: t('info_filter.deleted') });
      await refresh();
    } catch {
      if (dead.current) return;
      setOpMsg({ kind: 'err', text: t('info_filter.network_error') });
    }
  };

  const runPreview = async () => {
    if (!previewName.trim()) return;
    try {
      const d = await previewInfoFilter({
        category: previewCat.trim(),
        source_name: previewName.trim(),
      });
      if (dead.current) return;
      setPreviewResult(d);
    } catch {
      if (dead.current) return;
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

      <InfoFilterAddForm
        t={t}
        rulesCount={rules.length}
        enabledCount={rules.filter(r => r.enabled).length}
        ruleType={newRuleType}
        matchKind={newMatchKind}
        matchValue={newMatchValue}
        note={newNote}
        onRuleTypeChange={setNewRuleType}
        onMatchKindChange={setNewMatchKind}
        onMatchValueChange={setNewMatchValue}
        onNoteChange={setNewNote}
        onCreate={createRule}
      />

      <InfoFilterRuleList
        t={t}
        loading={loading}
        rules={rules}
        onToggle={toggleRule}
        onDelete={deleteRule}
      />

      <InfoFilterPreview
        t={t}
        category={previewCat}
        sourceName={previewName}
        result={previewResult}
        onCategoryChange={setPreviewCat}
        onSourceNameChange={setPreviewName}
        onRun={runPreview}
      />
    </div>
  );
}