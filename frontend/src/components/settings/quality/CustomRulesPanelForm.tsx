/**
 * quality/CustomRulesPanelForm — 新建/编辑规则表单区块 (拆分自 CustomRulesPanel.tsx)
 *
 * 纯展示 + 受控表单, 状态与提交逻辑仍由 CustomRulesPanel 持有 (零行为变更)。
 */
import type { Dispatch, SetStateAction } from 'react';
import { EMPTY_FORM, EXPERT_KINDS, FormState } from './CustomRulesPanel.types';

interface CustomRulesPanelFormProps {
  form: FormState;
  setForm: Dispatch<SetStateAction<FormState>>;
  editingId: number | null;
  setEditingId: Dispatch<SetStateAction<number | null>>;
  busy: boolean;
  submit: () => void;
}

export function CustomRulesPanelForm({
  form, setForm, editingId, setEditingId, busy, submit,
}: CustomRulesPanelFormProps) {
  return (
    <div className="st-rule" data-testid="custom-rule-form">
      <div>
        <p className="st-label">{editingId == null ? '新建规则' : `编辑规则 #${editingId}`}</p>
        <div className="st-ctrlrow">
          <select className="st-input" value={form.rule_kind} aria-label="规则类型"
            onChange={e => {
              const kind = e.target.value as FormState['rule_kind'];
              setForm(f => ({
                ...f, rule_kind: kind,
                match_kind: kind === 'semantic' ? 'nl' : 'title_contains',
              }));
            }}>
            <option value="expert">专家规则</option>
            <option value="semantic">AI 语义规则</option>
          </select>
          {form.rule_kind === 'expert' && (
            <select className="st-input" value={form.match_kind} aria-label="匹配方式"
              onChange={e => setForm(f => ({ ...f, match_kind: e.target.value }))}>
              {EXPERT_KINDS.map(([k, label]) => <option key={k} value={k}>{label}</option>)}
            </select>
          )}
          {form.rule_kind === 'expert' && (
            <select className="st-input" value={form.action} aria-label="动作"
              onChange={e => setForm(f => ({ ...f, action: e.target.value as FormState['action'] }))}>
              <option value="flag">扣分</option>
              <option value="reject">拒收 (strict 生效)</option>
            </select>
          )}
          <input type="number" min={0} max={100} className="st-input" style={{ maxWidth: 80 }}
            value={form.deduction} aria-label="扣分"
            onChange={e => setForm(f => ({ ...f, deduction: parseInt(e.target.value, 10) || 0 }))} />
        </div>
      </div>
      <div className="st-ctrl" style={{ flexDirection: 'column', alignItems: 'stretch', gap: 6 }}>
        <input className="st-input" placeholder="规则名称" aria-label="规则名称"
          value={form.name}
          onChange={e => setForm(f => ({ ...f, name: e.target.value }))} />
        <textarea className="st-input" rows={2}
          placeholder={form.rule_kind === 'semantic' ? '用自然语言描述违规判定标准' : '匹配值'}
          aria-label="匹配值" value={form.match_value}
          onChange={e => setForm(f => ({ ...f, match_value: e.target.value }))} />
        <input className="st-input" placeholder="限定分类 (留空=全部)" aria-label="限定分类"
          value={form.scope_category}
          onChange={e => setForm(f => ({ ...f, scope_category: e.target.value }))} />
        <div className="st-ctrlrow">
          <button type="button" className="st-btn primary" disabled={busy} onClick={submit}>
            {editingId == null ? '创建规则' : '保存修改'}
          </button>
          {editingId != null && (
            <button type="button" className="st-btn" disabled={busy}
              onClick={() => { setEditingId(null); setForm(EMPTY_FORM); }}>取消</button>
          )}
        </div>
      </div>
    </div>
  );
}