/**
 * quality/CustomRulesPanel — 两层质量规则管理面 (v0.8.6 P2)
 *
 * 专家规则 (确定性 matcher, 零 LLM) + AI 语义规则 (NL → 聚合单次 LLM 判别):
 * - 规则 CRUD: GET/POST/PUT/DELETE /api/quality/custom-rules
 * - gate 清单 + 开关: GET /gates; 开关写 PUT /api/quality/rules
 *   (quality.gate.<name>.enabled, 后端 5s TTL 缓存生效)
 * - dry-run: POST /dry-run — 专家确定性抽样; 语义侧 LLM 每次 cap 5 条
 *
 * 语义全局开关/预算 (quality.semantic_rules.*) 在 QualityRulesPanel 通用列表维护。
 */
import { useCallback, useEffect, useState } from 'react';
import {
  createCustomRule,
  deleteCustomRule,
  dryRunCustomRules,
  getCustomRuleGates,
  getCustomRules,
  putQualityRules,
  updateCustomRule,
} from '../../../api/settingsQuality';
import { CustomRulesPanelDryRun } from './CustomRulesPanelDryRun';
import { CustomRulesPanelForm } from './CustomRulesPanelForm';
import {
  EMPTY_FORM, CustomRule, DryRunResult, FormState, GateInfo,
} from './CustomRulesPanel.types';

export type { CustomRule, GateInfo } from './CustomRulesPanel.types';

export function CustomRulesPanel({ open }: { open: boolean }) {
  const [rules, setRules] = useState<CustomRule[]>([]);
  const [gates, setGates] = useState<GateInfo[]>([]);
  const [form, setForm] = useState<FormState>(EMPTY_FORM);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<{ type: 'ok' | 'error'; text: string } | null>(null);
  const [dryRun, setDryRun] = useState<DryRunResult | null>(null);
  const [withSemantic, setWithSemantic] = useState(false);

  const load = useCallback(async () => {
    try {
      const [r, g] = await Promise.all([
        getCustomRules<{ rules: CustomRule[] }>(),
        getCustomRuleGates<{ gates: GateInfo[] }>(),
      ]);
      setRules(r.rules || []);
      setGates(g.gates || []);
    } catch {
      setMsg({ type: 'error', text: '规则加载失败' });
    }
  }, []);

  useEffect(() => {
    if (open) void load();
  }, [open, load]);

  const submit = useCallback(async () => {
    if (!form.name.trim() || !form.match_value.trim()) {
      setMsg({ type: 'error', text: '名称与匹配值不能为空' });
      return;
    }
    setBusy(true);
    setMsg(null);
    try {
      const payload = form.rule_kind === 'semantic'
        ? { ...form, match_kind: 'nl', action: 'flag' as const }
        : form;
      if (editingId == null) {
        await createCustomRule(payload);
      } else {
        await updateCustomRule(editingId, payload);
      }
      setForm(EMPTY_FORM);
      setEditingId(null);
      setMsg({ type: 'ok', text: editingId == null ? '规则已创建' : '规则已更新' });
      await load();
    } catch {
      setMsg({ type: 'error', text: '保存失败' });
    } finally {
      setBusy(false);
    }
  }, [form, editingId, load]);

  const toggleRule = useCallback(async (r: CustomRule) => {
    setBusy(true);
    try {
      await updateCustomRule(r.id, { enabled: !r.enabled });
      await load();
    } catch {
      setMsg({ type: 'error', text: '切换失败' });
    } finally {
      setBusy(false);
    }
  }, [load]);

  const removeRule = useCallback(async (id: number) => {
    setBusy(true);
    try {
      await deleteCustomRule(id);
      if (editingId === id) { setEditingId(null); setForm(EMPTY_FORM); }
      await load();
    } catch {
      setMsg({ type: 'error', text: '删除失败' });
    } finally {
      setBusy(false);
    }
  }, [load, editingId]);

  const toggleGate = useCallback(async (g: GateInfo) => {
    setBusy(true);
    try {
      await putQualityRules({ [`quality.gate.${g.name}.enabled`]: !g.enabled });
      await load();
    } catch {
      setMsg({ type: 'error', text: '开关切换失败' });
    } finally {
      setBusy(false);
    }
  }, [load]);

  const runDry = useCallback(async () => {
    setBusy(true);
    setMsg(null);
    try {
      const d = await dryRunCustomRules<DryRunResult>({ limit: 20, with_semantic: withSemantic });
      setDryRun(d);
    } catch {
      setMsg({ type: 'error', text: 'dry-run 失败' });
    } finally {
      setBusy(false);
    }
  }, [withSemantic]);

  return (
    <section className="st-section" aria-label="自定义质量规则" data-testid="custom-rules-panel">
      <h3>自定义质量规则 ({rules.length})</h3>
      <p className="st-section-desc">
        专家规则 = 确定性匹配 (零 LLM); AI 语义规则 = 自然语言经 LLM 聚合判别
        (全局开关与预算在上方"质量设置"里, LLM 失败时 fail-open 放行并打标)。
      </p>
      <div className="st-section-body">
        {/* 规则列表 */}
        {rules.length === 0 ? (
          <p className="st-cellnote">暂无自定义规则</p>
        ) : rules.map(r => (
          <div key={r.id} className="st-rule" data-testid={`custom-rule-${r.id}`}>
            <div>
              <p className="st-label">
                <span className={`st-tag ${r.rule_kind === 'semantic' ? 'warn' : ''}`}>
                  {r.rule_kind === 'semantic' ? 'AI语义' : '专家'}
                </span>
                {' '}{r.name}
                {!r.enabled && ' (已停用)'}
              </p>
              <p className="st-key">
                {r.rule_kind === 'semantic' ? '语义: ' : `${r.match_kind}: `}
                {r.match_value} · {r.action === 'reject' ? '拒收' : '扣分'}
                {-r.deduction}
                {r.scope_category ? ` · 限 ${r.scope_category}` : ''}
              </p>
            </div>
            <div className="st-ctrl">
              <button type="button" role="switch" aria-checked={r.enabled}
                onClick={() => toggleRule(r)} className="st-switch"
                style={{ width: 32, height: 18 }} aria-label={`toggle ${r.name}`} />
              <button type="button" className="st-btn" disabled={busy}
                onClick={() => {
                  setEditingId(r.id);
                  setForm({
                    name: r.name, rule_kind: r.rule_kind,
                    match_kind: r.rule_kind === 'semantic' ? 'nl' : r.match_kind,
                    match_value: r.match_value, action: r.action,
                    deduction: r.deduction, scope_category: r.scope_category,
                  });
                }}>编辑</button>
              <button type="button" className="st-btn danger" disabled={busy}
                onClick={() => removeRule(r.id)}>删除</button>
            </div>
          </div>
        ))}

        {/* 新建 / 编辑表单 */}
        <CustomRulesPanelForm
          form={form} setForm={setForm}
          editingId={editingId} setEditingId={setEditingId}
          busy={busy} submit={submit}
        />

        {/* gate 开关 */}
        <div className="st-rule" data-testid="gate-toggles">
          <div>
            <p className="st-label">门禁开关 (14 个, 含上述三层)</p>
            <p className="st-key">关闭即跳过该 gate (改后 ~5s 生效)</p>
          </div>
          <div className="st-ctrl" style={{ flexWrap: 'wrap', justifyContent: 'flex-end', gap: 6 }}>
            {gates.map(g => (
              <label key={g.name} className="st-ctrlrow" style={{ gap: 4 }}>
                <input type="checkbox" checked={g.enabled} disabled={busy}
                  aria-label={`gate ${g.name}`}
                  onChange={() => toggleGate(g)} />
                <span className="st-cellk">{g.name} ({g.tier})</span>
              </label>
            ))}
          </div>
        </div>

        {/* dry-run */}
        <div className="st-rule" data-testid="dry-run-bar">
          <div>
            <p className="st-label">dry-run 预演</p>
            <p className="st-key">对最近入库 20 条抽样; 勾选语义时 LLM 最多判 5 条</p>
          </div>
          <div className="st-ctrl">
            <label className="st-ctrlrow" style={{ gap: 4 }}>
              <input type="checkbox" checked={withSemantic} aria-label="含语义判别"
                onChange={e => setWithSemantic(e.target.checked)} />
              <span className="st-cellk">含语义判别</span>
            </label>
            <button type="button" className="st-btn primary" disabled={busy} onClick={runDry}>
              {busy ? '运行中...' : '运行 dry-run'}
            </button>
          </div>
        </div>
        <CustomRulesPanelDryRun dryRun={dryRun} />

        <div className="st-actionbar">
          {msg && <span className={`st-ab-msg ${msg.type === 'ok' ? 'ok' : 'bad'}`}>{msg.text}</span>}
        </div>
      </div>
    </section>
  );
}

export default CustomRulesPanel;