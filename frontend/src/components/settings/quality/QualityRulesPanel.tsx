/**
 * quality/QualityRulesPanel — 通用质量规则 (Phase 5)
 *
 * 数据源: GET /api/quality/rules
 * 写入: PUT /api/quality/rules
 *
 * 设计: st-rule 行式布局, 每行一个 st-label + st-key + 控件;
 *       控件按 rule.value 类型渲染: boolean → st-switch, number → st-input,
 *       sample_rate → range slider, 其余 → st-input text
 */
import { useState, useCallback } from 'react';

export interface QualityRule {
  key: string;
  value: string | number | boolean;
  default: string | number | boolean;
}

export interface QualityRulesPanelProps {
  initialRules: QualityRule[];
}

export function QualityRulesPanel({ initialRules }: QualityRulesPanelProps) {
  const [rules, setRules] = useState<QualityRule[]>(initialRules);
  const [editing, setEditing] = useState<Record<string, any>>(() => {
    const init: Record<string, any> = {};
    for (const r of initialRules) init[r.key] = r.value;
    return init;
  });
  const [saving, setSaving] = useState(false);
  const [msg, setMsg] = useState<{ type: 'ok' | 'error'; text: string } | null>(null);

  const setVal = (key: string, val: any) => setEditing(prev => ({ ...prev, [key]: val }));

  const save = useCallback(async () => {
    setSaving(true);
    setMsg(null);
    try {
      const changed: Record<string, any> = {};
      for (const r of rules) {
        if (editing[r.key] !== r.value) changed[r.key] = editing[r.key];
      }
      if (Object.keys(changed).length === 0) {
        setMsg({ type: 'ok', text: '无变更' });
        setSaving(false);
        return;
      }
      const r = await fetch('/api/quality/rules', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ rules: changed }),
      });
      const d = await r.json();
      if (r.ok && d.status === 'ok') {
        setMsg({ type: 'ok', text: `已更新: ${d.updated?.join(', ') || 'OK'}` });
        const r2 = await fetch('/api/quality/rules');
        const d2 = await r2.json();
        const refreshed = (d2.rules || []) as QualityRule[];
        setRules(refreshed);
        const init: Record<string, any> = {};
        for (const r of refreshed) init[r.key] = r.value;
        setEditing(init);
      } else {
        setMsg({ type: 'error', text: d.message || '保存失败' });
      }
    } catch {
      setMsg({ type: 'error', text: '保存失败' });
    } finally {
      setSaving(false);
    }
  }, [rules, editing]);

  return (
    <section className="st-section" aria-label="通用质量规则" data-testid="quality-rules-panel">
      <h3>质量设置 ({rules.length})</h3>
      <p className="st-section-desc">
        通用质量规则 — 改即生效, 无需重启; 修改后点下方"应用质量配置"提交。
      </p>
      <div className="st-section-body">
        {rules.length === 0 ? (
          <p className="st-cellnote">加载中...</p>
        ) : rules.map(rule => (
          <div key={rule.key} className="st-rule">
            <div>
              <p className="st-label">{rule.key.replace(/^quality\./, '')}</p>
              <p className="st-key">{rule.key}</p>
            </div>
            <div className="st-ctrl">
              <RuleInput rule={rule} value={editing[rule.key]} onChange={v => setVal(rule.key, v)} />
            </div>
          </div>
        ))}
        <div className="st-actionbar">
          {msg && <span className={`st-ab-msg ${msg.type === 'ok' ? 'ok' : 'bad'}`}>{msg.text}</span>}
          <button type="button" className="st-btn primary" onClick={save} disabled={saving}>
            {saving ? '保存中...' : '应用质量配置'}
          </button>
        </div>
      </div>
    </section>
  );
}

function RuleInput({ rule, value, onChange }: {
  rule: QualityRule;
  value: any;
  onChange: (v: any) => void;
}) {
  if (typeof value === 'boolean') {
    return (
      <button
        type="button"
        role="switch"
        aria-checked={value}
        onClick={() => onChange(!value)}
        className="st-switch"
        style={{ width: 32, height: 18 }}
        aria-label={`toggle ${rule.key}`}
      />
    );
  }
  if (typeof value === 'number') {
    if (rule.key.includes('sample_rate')) {
      return (
        <div className="st-ctrlrow" style={{ width: '100%' }}>
          <input
            type="range" min={0} max={1} step={0.05}
            value={value}
            onChange={e => onChange(parseFloat(e.target.value))}
            className="flex-1"
            aria-label={`${rule.key} slider`}
          />
          <span className="st-cellk" style={{ minWidth: 40, textAlign: 'right' }}>
            {(value * 100).toFixed(0)}%
          </span>
        </div>
      );
    }
    return (
      <input
        type="number"
        value={value}
        onChange={e => onChange(parseFloat(e.target.value) || 0)}
        className="st-input"
        style={{ maxWidth: 120 }}
        aria-label={rule.key}
      />
    );
  }
  return (
    <input
      type="text"
      value={String(value)}
      onChange={e => onChange(e.target.value)}
      className="st-input"
      aria-label={rule.key}
    />
  );
}

export default QualityRulesPanel;