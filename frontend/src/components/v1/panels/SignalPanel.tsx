/**
 * SignalPanel — 资料层「受管信号」区块 (v0.8.5 C3, spec = docs/v0.8.5/V0.8.5_PLAN.md §6.1)
 *
 * 数据: GET /api/v1/signals?days=7&limit=50 (真实 API, 无 mock fallback)。
 * 动作: 每条「立项」POST /api/v1/cases (携带信号摘要) → 跳 /cases/{id} (判断层深链)。
 * 状态: loading / unavailable / empty(空数组合法 — B1 未贯通) / data。
 * 设计纪律: 三层区块 + 无新视觉 token (index.css 语义变量 + Tailwind, 同 CaseDetail 模式)。
 */
import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { listSignals, createCase, type V1Signal } from '../../../api/v1';
import { useToast } from '../../Toast';

function PanelBadge({ children, tone }: { children: React.ReactNode; tone: 'green' | 'blue' | 'gray' | 'red' }) {
  const fg = tone === 'green' ? 'var(--color-success)' : tone === 'blue' ? 'var(--color-info)' : tone === 'red' ? 'var(--color-error)' : 'var(--text-secondary)';
  const bg = `color-mix(in srgb, ${fg} 14%, transparent)`;
  return (
    <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium" style={{ background: bg, color: fg }}>
      {children}
    </span>
  );
}

export function SignalPanel() {
  const navigate = useNavigate();
  const toast = useToast();
  const [signals, setSignals] = useState<V1Signal[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [creatingFor, setCreatingFor] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    listSignals({ days: 7, limit: 50 })
      .then(r => { if (!cancelled) setSignals(r.items || []); })
      .catch(e => { if (!cancelled) { setError(e instanceof Error ? e.message : String(e)); setSignals([]); } })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, []);

  // 立项: 信号 → Case (title ≤120 / question ≤500, CreateCaseRequest 校验;
  // P1 修复: question 整体截断到 500, 仅 slice summary 时前缀+id 仍可超限)
  const openCase = async (s: V1Signal) => {
    setCreatingFor(s.id);
    try {
      const question = `信号 ${s.id} (subject: ${s.subject_name || s.subject_id}) 是否需要研判与行动? 原始摘要: ${s.summary.slice(0, 400)}`.slice(0, 500);
      const r = await createCase({
        title: s.summary.slice(0, 120),
        question,
        priority: 'p2',
        source: 'signal',
        related_signal_ids: [s.id],
      });
      toast.show({ type: 'success', message: '事项已建立, 进入判断层' });
      navigate(`/cases/${r.item.id}`);
    } catch (e) {
      toast.show({ type: 'error', message: `立项失败: ${e instanceof Error ? e.message : String(e)}` });
    } finally {
      setCreatingFor(null);
    }
  };

  return (
    <section aria-label="受管信号 (v1.0 能力区块)" data-testid="signal-panel"
      style={{ marginTop: 22, padding: '14px 16px', borderRadius: 10, border: '1px solid var(--sn-line, var(--line))', background: 'var(--sn-bg-panel, var(--bg-card))' }}>
      <header className="flex items-center gap-2 mb-3">
        <span className="text-xs font-bold uppercase tracking-wider num" style={{ color: 'var(--sn-mint, var(--color-success))' }}>受管信号</span>
        <span className="text-xs num" style={{ color: 'var(--sn-ink-3, var(--text-muted))' }}>SIGNALS · 近 7 天 · SK-01 供给</span>
        {loading && <span className="text-xs" style={{ color: 'var(--sn-ink-3, var(--text-muted))' }}>加载中…</span>}
      </header>

      {error && (
        <div className="text-sm p-3 rounded" style={{ background: 'color-mix(in srgb, var(--color-warning) 14%, transparent)', color: 'var(--text-primary)' }}>
          信号不可用 (unavailable): {error}
        </div>
      )}
      {!error && !loading && signals.length === 0 && (
        <div className="text-sm" style={{ color: 'var(--sn-ink-3, var(--text-muted))' }}>
          近 7 天无受管信号 (采集→准入→信号链路未贯通属预期, D1 点火验收后此处出现真实供给)
        </div>
      )}
      {!error && signals.length > 0 && (
        <ul className="space-y-2">
          {signals.map(s => (
            <li key={s.id} className="flex items-start justify-between gap-3 p-3 rounded border" style={{ borderColor: 'var(--sn-line, var(--line))' }}>
              <div className="flex-1 min-w-0">
                <div className="text-sm font-medium truncate" style={{ color: 'var(--sn-ink, var(--text-primary))' }}>{s.summary}</div>
                <div className="text-xs mt-1 font-mono" style={{ color: 'var(--sn-ink-3, var(--text-muted))' }}>
                  {s.occurred_at} · {s.subject_name || s.subject_id} → material:{s.material_id} · {s.status}
                </div>
              </div>
              <div className="flex items-center gap-2 shrink-0">
                <PanelBadge tone={s.confidence === 'verified' ? 'green' : s.confidence === 'likely' ? 'blue' : 'gray'}>{s.confidence}</PanelBadge>
                <button
                  type="button"
                  onClick={() => openCase(s)}
                  disabled={creatingFor === s.id}
                  className="text-xs px-2.5 py-1 rounded font-medium focus-ring disabled:opacity-50"
                  style={{ background: 'var(--sn-mint, var(--color-success))', color: 'var(--text-on-success, #fff)' }}
                  data-testid="signal-open-case-btn"
                >
                  {creatingFor === s.id ? '立项中…' : '立项'}
                </button>
              </div>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
