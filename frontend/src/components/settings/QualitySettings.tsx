/**
 * QualitySettings — 质量规则折叠区（Phase 5）。
 *
 * Phase 1B: 拆自原 SettingsPanel.tsx 质量设置段。
 * 包含质量规则列表 + 多种输入类型（boolean/number/text/sample_rate slider）。
 * 自包含状态 + handlers；通过 props.open 触发数据加载。
 */
import React, { useState, useEffect, useCallback } from 'react';

export interface QualityRule {
  key: string;
  value: string | number | boolean;
  default: string | number | boolean;
}

interface QualitySettingsProps {
  open: boolean;
}

type QualityMessage = { type: 'ok' | 'error'; text: string } | null;

export function QualitySettings({ open }: QualitySettingsProps) {
  const [qualityOpen, setQualityOpen] = useState(false);
  const [qualityRules, setQualityRules] = useState<QualityRule[]>([]);
  const [qualityEditing, setQualityEditing] = useState<Record<string, any>>({});
  const [savingQuality, setSavingQuality] = useState(false);
  const [qualityMessage, setQualityMessage] = useState<QualityMessage>(null);

  // 打开面板时拉质量规则
  useEffect(() => {
    if (!open) return;
    fetch('/api/quality/rules')
      .then(r => r.json())
      .then(data => {
        const rules = (data.rules || []) as QualityRule[];
        setQualityRules(rules);
        const init: Record<string, any> = {};
        for (const r of rules) init[r.key] = r.value;
        setQualityEditing(init);
      })
      .catch(() => setQualityMessage({ type: 'error', text: '加载质量配置失败' }));
  }, [open]);

  const saveQuality = useCallback(async () => {
    setSavingQuality(true);
    setQualityMessage(null);
    try {
      const rules: Record<string, any> = {};
      for (const r of qualityRules) {
        if (qualityEditing[r.key] !== r.value) {
          rules[r.key] = qualityEditing[r.key];
        }
      }
      if (Object.keys(rules).length === 0) {
        setQualityMessage({ type: 'ok', text: '无变更' });
        setSavingQuality(false);
        return;
      }
      const resp = await fetch('/api/quality/rules', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ rules }),
      });
      const data = await resp.json();
      if (resp.ok && data.status === 'ok') {
        setQualityMessage({ type: 'ok', text: `已更新: ${data.updated?.join(', ') || 'OK'}` });
        // 重新拉取
        const r2 = await fetch('/api/quality/rules');
        const d2 = await r2.json();
        const refreshed = (d2.rules || []) as QualityRule[];
        setQualityRules(refreshed);
        const init: Record<string, any> = {};
        for (const r of refreshed) init[r.key] = r.value;
        setQualityEditing(init);
      } else {
        setQualityMessage({ type: 'error', text: data.message || '保存失败' });
      }
    } catch {
      setQualityMessage({ type: 'error', text: '保存失败' });
    } finally {
      setSavingQuality(false);
    }
  }, [qualityRules, qualityEditing]);

  function renderQualityInput(rule: QualityRule) {
    const v = qualityEditing[rule.key];
    const setV = (val: any) => setQualityEditing(prev => ({ ...prev, [rule.key]: val }));
    if (typeof v === 'boolean') {
      return (
        <button
          onClick={() => setV(!v)}
          className="px-2 py-0.5 text-xs rounded-[var(--radius-sm)]"
          style={{
            backgroundColor: v ? 'var(--color-ai)' : 'var(--bg-hover)',
            color: v ? 'var(--text-on-color)' : 'var(--text-secondary)',
            border: `1px solid ${v ? 'var(--color-ai)' : 'var(--border-color)'}`,
            minWidth: 44,
          }}
        >
          {v ? '已开启' : '已关闭'}
        </button>
      );
    }
    if (typeof v === 'number') {
      if (rule.key.includes('sample_rate')) {
        return (
          <input
            type="range" min={0} max={1} step={0.05}
            value={v}
            onChange={e => setV(parseFloat(e.target.value))}
            className="flex-1"
          />
        );
      }
      return (
        <input
          type="number" value={v}
          onChange={e => setV(parseFloat(e.target.value) || 0)}
          className="w-20 px-2 py-0.5 text-xs rounded-[var(--radius-sm)] focus-ring"
          style={{ backgroundColor: 'var(--bg-hover)', border: '1px solid var(--border-color)', color: 'var(--text-primary)' }}
        />
      );
    }
    return (
      <input
        type="text" value={String(v)}
        onChange={e => setV(e.target.value)}
        className="flex-1 px-2 py-0.5 text-xs rounded-[var(--radius-sm)] focus-ring"
        style={{ backgroundColor: 'var(--bg-hover)', border: '1px solid var(--border-color)', color: 'var(--text-primary)' }}
      />
    );
  }

  return (
    <div className="rounded-[var(--radius-sm)]" style={{ border: '1px solid var(--border-color)' }}>
      <button
        onClick={() => setQualityOpen(o => !o)}
        className="w-full flex items-center justify-between px-3 py-2 text-xs"
        style={{ color: 'var(--text-primary)' }}
      >
        <span className="font-medium">质量设置 ({qualityRules.length})</span>
        <span style={{ color: 'var(--text-muted)' }}>{qualityOpen ? '−' : '+'}</span>
      </button>
      {qualityOpen && (
        <div className="px-3 py-2 space-y-2" style={{ borderTop: '1px solid var(--border-color)' }}>
          {qualityRules.length === 0 ? (
            <p className="text-[10px]" style={{ color: 'var(--text-muted)' }}>加载中...</p>
          ) : qualityRules.map(rule => (
            <div key={rule.key} className="flex items-center gap-2">
              <span className="text-[11px] font-mono flex-1 truncate" style={{ color: 'var(--text-secondary)' }} title={rule.key}>
                {rule.key.replace(/^quality\./, '')}
              </span>
              {renderQualityInput(rule)}
            </div>
          ))}
          {qualityMessage && (
            <p className="text-[10px]" style={{ color: qualityMessage.type === 'ok' ? 'var(--color-general)' : 'var(--color-error)' }}>
              {qualityMessage.text}
            </p>
          )}
          <button
            onClick={saveQuality}
            disabled={savingQuality}
            className="w-full px-2 py-1 text-[11px] font-medium rounded-[var(--radius-sm)]"
            style={{
              backgroundColor: 'var(--color-ai)', color: 'var(--text-on-color)', border: 'none',
              opacity: savingQuality ? 0.6 : 1, marginTop: 4,
            }}
          >
            {savingQuality ? '保存中...' : '应用质量配置'}
          </button>
        </div>
      )}
    </div>
  );
}
