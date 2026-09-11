/**
 * SignalPanel — 资料层「受管信号」区块 (v0.8.5 C3/D1, spec = docs/v0.8.5/V0.8.5_PLAN.md §6.1)
 *
 * 数据: GET /api/v1/signals?days=7&limit=50 (真实 API, 无 mock fallback)。
 * 动作: 每条「立项」POST /api/v1/cases (携带 related_signal_ids → 自动绑定证据材料)
 *       → 跳 /cases/{id}；subject 名可点开「Subject 抽屉」(D1.3, 下钻该对象近期信号)。
 * 状态: loading / unavailable / empty(空数组合法 — B1 点火前) / data。
 */
import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { listSignals, createCase, type V1Signal } from '../../../api/v1';
import { PANEL_SHELL } from './panelShell';
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

/** D1.3 Subject 抽屉 — 下钻该对象近期信号 (GET /api/v1/signals?subject_id=) */
function SubjectDrawer({ subjectId, name, onClose }: { subjectId: string; name: string; onClose: () => void }) {
  const [items, setItems] = useState<V1Signal[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    listSignals({ subject_id: subjectId, days: 30, limit: 20 })
      .then(r => { if (!cancelled) setItems(r.items || []); })
      .catch(e => { if (!cancelled) setError(e instanceof Error ? e.message : String(e)); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [subjectId]);

  return (
    <div className="fixed inset-0 flex justify-end" style={{ zIndex: 'var(--z-modal)' }} role="dialog" aria-label={`Subject 抽屉: ${name}`} data-testid="subject-drawer">
      <div className="absolute inset-0" style={{ background: 'rgba(0,0,0,0.45)' }} onClick={onClose} aria-label="关闭抽屉" />
      <aside className="relative w-full max-w-md h-full overflow-y-auto p-5"
        style={{ background: 'var(--bg-card)', borderLeft: '1px solid var(--line)' }}>
        <header className="flex items-start justify-between mb-4">
          <div>
            <div className="text-xs font-bold uppercase tracking-wider num" style={{ color: 'var(--color-info)' }}>SUBJECT</div>
            <div className="text-base font-semibold mt-0.5" style={{ color: 'var(--text-primary)' }}>{name}</div>
            <div className="text-xs mt-1 font-mono" style={{ color: 'var(--text-muted)' }}>{subjectId}</div>
          </div>
          <button type="button" onClick={onClose} className="text-sm px-2 py-1 rounded"
            style={{ background: 'var(--bg-muted)', color: 'var(--text-secondary)' }} aria-label="关闭">✕</button>
        </header>
        <div className="text-xs uppercase tracking-wider num mb-2" style={{ color: 'var(--text-muted)' }}>近期信号 · 30 天</div>
        {loading && <div className="text-sm" style={{ color: 'var(--text-muted)' }}>加载中…</div>}
        {error && <div className="text-sm p-3 rounded" style={{ background: 'color-mix(in srgb, var(--color-warning) 14%, transparent)' }}>信号不可用 (unavailable): {error}</div>}
        {!loading && !error && items.length === 0 && (
          <div className="text-sm" style={{ color: 'var(--text-muted)' }}>近 30 天该对象无信号</div>
        )}
        <ul className="space-y-2">
          {items.map(s => (
            <li key={s.id} className="p-3 rounded border" style={{ borderColor: 'var(--line)' }}>
              <div className="text-sm" style={{ color: 'var(--text-primary)' }}>{s.summary}</div>
              <div className="text-xs mt-1 font-mono flex items-center gap-2" style={{ color: 'var(--text-muted)' }}>
                {s.occurred_at}
                <PanelBadge tone={s.confidence === 'verified' ? 'green' : s.confidence === 'likely' ? 'blue' : 'gray'}>{s.confidence}</PanelBadge>
              </div>
            </li>
          ))}
        </ul>
      </aside>
    </div>
  );
}

export function SignalPanel() {
  const navigate = useNavigate();
  const toast = useToast();
  const [signals, setSignals] = useState<V1Signal[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [creatingFor, setCreatingFor] = useState<string | null>(null);
  const [drawer, setDrawer] = useState<{ subjectId: string; name: string } | null>(null);

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
      style={PANEL_SHELL}>
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
                <div className="text-xs mt-1 font-mono flex items-center gap-2" style={{ color: 'var(--sn-ink-3, var(--text-muted))' }}>
                  <span>{s.occurred_at}</span>
                  <button type="button"
                    onClick={() => setDrawer({ subjectId: s.subject_id, name: s.subject_name || s.subject_id })}
                    className="underline decoration-dotted focus-ring"
                    style={{ color: 'var(--color-info)' }}
                    data-testid="signal-subject-btn"
                    aria-label={`查看 subject ${s.subject_name || s.subject_id} 的近期信号`}
                  >
                    {s.subject_name || s.subject_id}
                  </button>
                  <span>→ material:{s.material_id} · {s.status}</span>
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
      {drawer && (
        <SubjectDrawer subjectId={drawer.subjectId} name={drawer.name} onClose={() => setDrawer(null)} />
      )}
    </section>
  );
}
