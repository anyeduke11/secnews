/**
 * settings/AlertSettings — 告警规则设置。
 *
 * 拆自原 SettingsPage.tsx (1065 行) 中 AlertSettings (~386-456 行)。
 * 纯结构拆分: 状态与 fetch/渲染逻辑逐字迁移。
 */
import React, { useState, useEffect } from 'react';

export function AlertSettings() {
  const [rules, setRules] = useState<any[]>([]);
  const [count, setCount] = useState(0);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetch('/api/alerts/rules')
      .then(r => r.json())
      .then(d => {
        setRules(d.items || []);
        setCount(d.count || 0);
      })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  const handleToggle = async (rule: any) => {
    try {
      await fetch(`/api/alerts/rules/${rule.id}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ enabled: !rule.enabled }),
      });
      setRules(prev => prev.map(r => r.id === rule.id ? { ...r, enabled: !r.enabled } : r));
    } catch {}
  };

  return (
    <div className="space-y-2">
      <div className="card-compact">
        <div className="px-2.5 py-1.5">
          <div className="flex items-center justify-between mb-1.5">
            <span className="text-[11px] font-medium" style={{ color: 'var(--text-primary)' }}>告警规则 ({count})</span>
          </div>
          {loading ? (
            <p className="text-[9px]" style={{ color: 'var(--text-muted)' }}>加载中...</p>
          ) : rules.length === 0 ? (
            <p className="text-[9px]" style={{ color: 'var(--text-muted)' }}>暂无告警规则</p>
          ) : (
            <div className="space-y-0.5">
              {rules.map((rule: any) => (
                <div key={rule.id} className="flex items-center gap-1.5 px-1.5 py-1 rounded-[var(--radius-sm)]" style={{ backgroundColor: 'var(--bg-hover)' }}>
                  <span className="text-[9px] font-mono flex-1 truncate" style={{ color: 'var(--text-primary)' }} title={rule.name}>
                    {rule.name}
                  </span>
                  <span className="text-[8px] font-mono" style={{ color: 'var(--text-muted)' }}>
                    {rule.cooldown_sec ? `${Math.round(rule.cooldown_sec / 3600)}h` : '-'}
                  </span>
                  <button
                    onClick={() => handleToggle(rule)}
                    className="text-[9px] px-1.5 py-0.5 rounded"
                    style={{
                      backgroundColor: rule.enabled ? 'color-mix(in srgb, var(--color-success) 9%, transparent)' : 'transparent',
                      color: rule.enabled ? 'var(--color-success)' : 'var(--text-muted)',
                      border: `1px solid ${rule.enabled ? 'var(--color-success)' : 'var(--border-color)'}`,
                    }}
                  >
                    {rule.enabled ? '开' : '关'}
                  </button>
                </div>
              ))}
            </div>
          )}
          <p className="text-[9px] mt-1.5" style={{ color: 'var(--text-muted)' }}>
            告警规则在采集时自动评估，触发后发送通知
          </p>
        </div>
      </div>
    </div>
  );
}
