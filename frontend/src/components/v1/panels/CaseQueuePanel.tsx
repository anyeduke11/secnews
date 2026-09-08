/**
 * CaseQueuePanel — 判断层「Case 队列」区块 (v0.8.5 C3, spec = docs/v0.8.5/V0.8.5_PLAN.md §6.2)
 *
 * 数据: GET /api/v1/cases?status=blocked&limit=50 + GET /api/v1/cases?status=open&status=in_progress&limit=50
 * (FastAPI list[str] 重复键语义, 禁止逗号写法 — FactCheck #2); blocked 置顶。
 * 动作: 点击 case → /cases/{id} 判断层深链接 (SentinelShell layer=judge)。
 * 状态: loading / unavailable / empty / data; 空数组合法 (v1_cases 表空属预期)。
 */
import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { listCases } from '../../../api/v1';
import type { Case } from '../../../domain/v1_0';

const ACTIVE: Case['status'][] = ['blocked', 'in_progress', 'open'];

export function CaseQueuePanel() {
  const navigate = useNavigate();
  const [cases, setCases] = useState<Case[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    Promise.all([
      listCases({ status: ['blocked'], limit: 50 }),
      listCases({ status: ['open', 'in_progress'], limit: 50 }),
    ])
      .then(([blocked, rest]) => {
        if (cancelled) return;
        // blocked 置顶; 组内 in_progress 先于 open
        const rank = (s?: string) => (s === 'blocked' ? 0 : s === 'in_progress' ? 1 : 2);
        const merged = [...(blocked.items || []), ...(rest.items || [])]
          .filter(c => ACTIVE.includes(c.status as Case['status']))
          .sort((a, b) => rank(a.status) - rank(b.status));
        setCases(merged);
      })
      .catch(e => { if (!cancelled) { setError(e instanceof Error ? e.message : String(e)); setCases([]); } })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, []);

  return (
    <section aria-label="Case 队列 (v1.0 能力区块)" data-testid="case-queue-panel"
      style={{ marginTop: 26, padding: '14px 16px', borderRadius: 10, border: '1px solid var(--sn-line, var(--line))', background: 'var(--sn-bg-panel, var(--bg-card))' }}>
      <header className="flex items-center gap-2 mb-3">
        <span className="text-xs font-bold uppercase tracking-wider num" style={{ color: 'var(--sn-amber, var(--color-warning))' }}>Case 队列</span>
        <span className="text-xs num" style={{ color: 'var(--sn-ink-3, var(--text-muted))' }}>CASES · 阻塞置顶 · 点击进入研判</span>
        {loading && <span className="text-xs" style={{ color: 'var(--sn-ink-3, var(--text-muted))' }}>加载中…</span>}
      </header>

      {error && (
        <div className="text-sm p-3 rounded" style={{ background: 'color-mix(in srgb, var(--color-warning) 14%, transparent)', color: 'var(--text-primary)' }}>
          队列不可用 (unavailable): {error}
        </div>
      )}
      {!error && !loading && cases.length === 0 && (
        <div className="text-sm" style={{ color: 'var(--sn-ink-3, var(--text-muted))' }}>
          无活跃事项 (从资料层信号「立项」或在业务链中创建后出现)
        </div>
      )}
      {!error && cases.length > 0 && (
        <ul className="space-y-2">
          {cases.map(c => (
            <li key={c.id}>
              <button
                type="button"
                onClick={() => navigate(`/cases/${c.id}`)}
                className="w-full text-left flex items-start justify-between gap-3 p-3 rounded border cursor-pointer hover:shadow-md transition-shadow focus-ring"
                style={{ borderColor: 'var(--sn-line, var(--line))', background: 'transparent' }}
                data-testid="case-queue-item"
              >
                <div className="flex-1 min-w-0">
                  <div className="text-sm font-medium truncate" style={{ color: 'var(--sn-ink, var(--text-primary))' }}>{c.title}</div>
                  <div className="text-xs mt-1 line-clamp-2" style={{ color: 'var(--sn-ink-3, var(--text-muted))' }}>{c.question}</div>
                  <div className="text-xs mt-1 font-mono" style={{ color: 'var(--sn-ink-3, var(--text-muted))' }}>{c.id} · rev {c.revision}</div>
                </div>
                <div className="flex items-center gap-2 shrink-0">
                  <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium"
                    style={{
                      background: `color-mix(in srgb, ${c.status === 'blocked' ? 'var(--color-warning)' : c.status === 'in_progress' ? 'var(--color-success)' : 'var(--color-info)'} 14%, transparent)`,
                      color: c.status === 'blocked' ? 'var(--color-warning)' : c.status === 'in_progress' ? 'var(--color-success)' : 'var(--color-info)',
                    }}>
                    {c.status === 'blocked' ? '阻塞' : c.status === 'in_progress' ? '进行中' : '待研判'}
                  </span>
                  <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium"
                    style={{
                      background: `color-mix(in srgb, ${c.priority === 'p0' ? 'var(--color-error)' : c.priority === 'p1' ? 'var(--color-warning)' : 'var(--text-muted)'} 14%, transparent)`,
                      color: c.priority === 'p0' ? 'var(--color-error)' : c.priority === 'p1' ? 'var(--color-warning)' : 'var(--text-secondary)',
                    }}>
                    {c.priority}
                  </span>
                </div>
              </button>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
