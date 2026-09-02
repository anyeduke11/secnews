/**
 * settings/AlertSettings — 告警规则设置 (V2 哨兵化)
 *
 * v0.7.x SettingsHub V2: st-section + st-table + st-switch 替换原 card-base
 */
import { useState, useEffect } from 'react';

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
    <section className="st-section" aria-label="告警规则" data-testid="alert-settings">
      <h3>告警规则 ({count})</h3>
      <p className="st-section-desc">告警规则在采集时自动评估, 触发后发送通知; cooldown 间隔内不重复。</p>
      <div className="st-section-body">
        {loading ? (
          <p className="st-cellnote">加载中...</p>
        ) : rules.length === 0 ? (
          <p className="st-cellnote">暂无告警规则</p>
        ) : (
          <table className="st-table" aria-label="告警规则列表">
            <thead>
              <tr>
                <th>规则</th>
                <th>冷却</th>
                <th style={{ width: 100 }}>启用</th>
              </tr>
            </thead>
            <tbody>
              {rules.map((rule: any) => (
                <tr key={rule.id} data-testid={`alert-row-${rule.id}`}>
                  <td>
                    <span className="st-nm">{rule.name}</span>
                  </td>
                  <td>{rule.cooldown_sec ? `${Math.round(rule.cooldown_sec / 3600)}h` : '—'}</td>
                  <td>
                    <button
                      type="button"
                      role="switch"
                      aria-checked={rule.enabled}
                      onClick={() => handleToggle(rule)}
                      className="st-switch"
                      style={{ width: 32, height: 18 }}
                      aria-label={`toggle ${rule.name}`}
                    />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </section>
  );
}

export default AlertSettings;