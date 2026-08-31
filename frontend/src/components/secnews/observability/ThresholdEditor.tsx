/**
 * ThresholdEditor — v0.7 Batch ④ 阈值规则编辑折叠面板.
 *
 * 4 大类规则 (api / llm / job / audit) 各有 warn / critical / window_minutes.
 * PUT /api/observability/thresholds (整块替换); 校验失败显示 400 错误.
 */
import { useEffect, useState } from 'react';

interface MetricSpec {
  warn?: number;
  critical?: number;
  window_minutes?: number;
}

interface Thresholds {
  api?: Record<string, MetricSpec>;
  llm?: Record<string, MetricSpec>;
  job?: Record<string, MetricSpec>;
  audit?: Record<string, MetricSpec>;
  alerts?: { channels?: string[]; cooldown_minutes?: number };
}

interface ThresholdsResp {
  thresholds: Thresholds;
  defaults: Thresholds;
  as_of: string;
}

const CATEGORIES: { key: keyof Thresholds; label: string; metrics: { id: string; label: string }[] }[] = [
  { key: 'api', label: 'API', metrics: [
    { id: 'error_rate_pct', label: '错误率 %' },
    { id: 'p95_latency_ms', label: 'p95 延迟 ms' },
  ]},
  { key: 'llm', label: 'LLM', metrics: [
    { id: 'error_rate_pct', label: '错误率 %' },
  ]},
  { key: 'job', label: '任务', metrics: [
    { id: 'failure_rate_pct', label: '失败率 %' },
  ]},
  { key: 'audit', label: '审计', metrics: [
    { id: 'llm_config_change_per_hour', label: 'LLM 配置变更/小时' },
  ]},
];

export function ThresholdEditor() {
  const [open, setOpen] = useState(false);
  const [rules, setRules] = useState<Thresholds | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  useEffect(() => {
    fetch('/api/observability/thresholds')
      .then((r) => (r.ok ? r.json() : null))
      .then((d: ThresholdsResp | null) => {
        if (d) setRules(d.thresholds);
      })
      .catch(() => {})
        .finally(() => setLoading(false));
  }, []);

  const updateSpec = (cat: keyof Thresholds, metric: string, field: keyof MetricSpec, value: string) => {
    setRules((prev) => {
      if (!prev) return prev;
      const next: Thresholds = { ...prev };
      const catRules: Record<string, MetricSpec> = { ...((next[cat] as Record<string, MetricSpec>) ?? {}) };
      const cur: MetricSpec = { ...(catRules[metric] ?? {}) };
      const num = value === '' ? undefined : Number(value);
      if (num === undefined || Number.isNaN(num)) {
        delete (cur as Record<string, unknown>)[field];
      } else {
        (cur as Record<string, unknown>)[field] = num;
      }
      catRules[metric] = cur;
      (next as Record<string, unknown>)[cat] = catRules;
      return next;
    });
  };

  const handleSave = async () => {
    if (!rules) return;
    setSaving(true);
    setMessage(null);
    try {
      const r = await fetch('/api/observability/thresholds', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ thresholds: rules }),
      });
      if (!r.ok) {
        const body = await r.json().catch(() => ({}));
        throw new Error(body.detail ?? `HTTP ${r.status}`);
      }
      setMessage('已保存');
    } catch (e) {
      setMessage(`保存失败: ${e instanceof Error ? e.message : String(e)}`);
    } finally {
      setSaving(false);
    }
  };

  if (loading) {
    return (
      <div className="text-xs font-mono" style={{ color: 'var(--text-muted)' }}>
        阈值规则加载中…
      </div>
    );
  }
  if (!rules) return null;

  return (
    <section
      className="p-4 rounded"
      style={{ backgroundColor: 'var(--bg-secondary)', border: '1px solid var(--border-light)' }}
    >
      <button
        className="text-xs font-mono mb-3 flex items-center gap-2"
        style={{ color: 'var(--text-primary)' }}
        onClick={() => setOpen((o) => !o)}
        data-testid="threshold-toggle"
      >
        <span>{open ? '▼' : '▶'}</span>
        <span>阈值规则 (点击展开 / 折叠)</span>
      </button>

      {open && (
        <div className="flex flex-col gap-3" data-testid="threshold-editor">
          {CATEGORIES.map((cat) => (
            <div key={cat.key} className="border-l-2 pl-3" style={{ borderColor: 'var(--border-light)' }}>
              <div className="text-xs font-mono mb-2" style={{ color: 'var(--text-muted)' }}>
                {cat.label}
              </div>
              {cat.metrics.map((m) => {
                const spec = (rules[cat.key] as Record<string, MetricSpec> | undefined)?.[m.id] ?? {};
                return (
                  <div key={m.id} className="flex items-center gap-2 mb-2 text-xs font-mono">
                    <span style={{ color: 'var(--text-primary)', minWidth: 180 }}>{m.label}</span>
                    <label className="flex items-center gap-1">
                      <span style={{ color: 'var(--text-muted)' }}>warn</span>
                      <input
                        type="number"
                        className="w-16 px-1 py-0.5 rounded"
                        style={{
                          backgroundColor: 'var(--bg-primary)',
                          border: '1px solid var(--border-light)',
                          color: 'var(--text-primary)',
                        }}
                        value={spec.warn ?? ''}
                        onChange={(e) => updateSpec(cat.key, m.id, 'warn', e.target.value)}
                        data-testid={`input-warn-${cat.key}-${m.id}`}
                      />
                    </label>
                    <label className="flex items-center gap-1">
                      <span style={{ color: 'var(--text-muted)' }}>critical</span>
                      <input
                        type="number"
                        className="w-16 px-1 py-0.5 rounded"
                        style={{
                          backgroundColor: 'var(--bg-primary)',
                          border: '1px solid var(--border-light)',
                          color: 'var(--text-primary)',
                        }}
                        value={spec.critical ?? ''}
                        onChange={(e) => updateSpec(cat.key, m.id, 'critical', e.target.value)}
                        data-testid={`input-critical-${cat.key}-${m.id}`}
                      />
                    </label>
                    <label className="flex items-center gap-1">
                      <span style={{ color: 'var(--text-muted)' }}>window(min)</span>
                      <input
                        type="number"
                        className="w-16 px-1 py-0.5 rounded"
                        style={{
                          backgroundColor: 'var(--bg-primary)',
                          border: '1px solid var(--border-light)',
                          color: 'var(--text-primary)',
                        }}
                        value={spec.window_minutes ?? ''}
                        onChange={(e) => updateSpec(cat.key, m.id, 'window_minutes', e.target.value)}
                      />
                    </label>
                  </div>
                );
              })}
            </div>
          ))}

          <div className="flex items-center gap-2 mt-2">
            <button
              className="px-3 py-1 rounded text-xs font-mono"
              style={{
                backgroundColor: 'var(--accent)',
                color: 'var(--bg-primary)',
                opacity: saving ? 0.6 : 1,
              }}
              onClick={handleSave}
              disabled={saving}
              data-testid="threshold-save"
            >
              {saving ? '保存中…' : '保存阈值'}
            </button>
            {message && (
              <span
                className="text-xs font-mono"
                style={{
                  color: message.startsWith('保存失败') ? 'var(--color-error)' : 'var(--color-success)',
                }}
                data-testid="threshold-message"
              >
                {message}
              </span>
            )}
          </div>
        </div>
      )}
    </section>
  );
}