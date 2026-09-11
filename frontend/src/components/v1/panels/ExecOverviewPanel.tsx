/**
 * ExecOverviewPanel — 行动层「执行与验收总览」区块 (v0.8.5 C3, spec = docs/v0.8.5/V0.8.5_PLAN.md §6.4)
 *
 * 数据: GET /api/v1/cases?status=open&status=in_progress&limit=8 → 并行
 *       GET /api/v1/cases/{id}/aggregate?actions_limit=20 (spec: limit=8 上限)。
 * 降级: 任一 case 聚合失败 → 该卡片显示 unavailable, 不显示 0 (spec §6.4, 批判性审查 #4)。
 * 动作: 点击 → /cases/{id}?section=actions。
 * 计数口径: 待批准 = action.status=planned; 运行中 = action.status=running;
 *           待验收 = artifact.status=verified (等待业务验收)。
 */
import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { listCases, getCaseAggregate, type CaseAggregate } from '../../../api/v1';
import { PANEL_SHELL } from './panelShell';

interface Slot {
  caseId: string;
  title: string;
  agg: CaseAggregate | null;   // null = 该 case 聚合拉取失败 → unavailable
  error?: string;
}

export function ExecOverviewPanel() {
  const navigate = useNavigate();
  const [slots, setSlots] = useState<Slot[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    (async () => {
      try {
        const r = await listCases({ status: ['open', 'in_progress'], limit: 8 });
        if (cancelled) return;
        const items = (r.items || []).slice(0, 8);
        // 并行聚合, 单 case 失败隔离为 unavailable 卡片 (不阻断其他, spec §6.4)
        const settled = await Promise.all(
          items.map(async (c): Promise<Slot> => {
            try {
              const agg = await getCaseAggregate(c.id, { actions_limit: 20 });
              return { caseId: c.id, title: c.title, agg };
            } catch (e) {
              return { caseId: c.id, title: c.title, agg: null, error: e instanceof Error ? e.message : String(e) };
            }
          })
        );
        if (!cancelled) setSlots(settled);
      } catch (e) {
        if (!cancelled) { setError(e instanceof Error ? e.message : String(e)); setSlots([]); }
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => { cancelled = true; };
  }, []);

  return (
    <section aria-label="执行与验收总览 (v1.0 能力区块)" data-testid="exec-overview-panel"
      style={PANEL_SHELL}>
      <header className="flex items-center gap-2 mb-3">
        <span className="text-xs font-bold uppercase tracking-wider num" style={{ color: 'var(--sn-mint, var(--color-success))' }}>执行与验收总览</span>
        <span className="text-xs num" style={{ color: 'var(--sn-ink-3, var(--text-muted))' }}>EXEC · SK-03/04 · 前 8 个活跃事项</span>
        {loading && <span className="text-xs" style={{ color: 'var(--sn-ink-3, var(--text-muted))' }}>加载中…</span>}
      </header>

      {error && (
        <div className="text-sm p-3 rounded" style={{ background: 'color-mix(in srgb, var(--color-warning) 14%, transparent)', color: 'var(--text-primary)' }}>
          总览不可用 (unavailable): {error}
        </div>
      )}
      {!error && !loading && slots.length === 0 && (
        <div className="text-sm" style={{ color: 'var(--sn-ink-3, var(--text-muted))' }}>
          无进行中的执行 (判断层批准行动后此处出现)
        </div>
      )}
      {!error && slots.length > 0 && (
        <ul className="grid grid-cols-1 md:grid-cols-2 gap-2">
          {slots.map(s => {
            if (!s.agg) {
              return (
                <li key={s.caseId} className="p-3 rounded border" style={{ borderColor: 'var(--sn-line, var(--line))' }}>
                  <div className="text-sm font-medium" style={{ color: 'var(--sn-ink, var(--text-primary))' }}>{s.title}</div>
                  <div className="text-xs mt-1" style={{ color: 'var(--sn-red, var(--color-error))' }}>
                    unavailable: {s.error?.slice(0, 80)}
                  </div>
                </li>
              );
            }
            const pendingApprove = s.agg.actions.filter(a => a.status === 'planned').length;
            const running = s.agg.actions.filter(a => a.status === 'running').length;
            const pendingAccept = s.agg.artifacts.filter(a => a.status === 'verified').length;
            const failed = s.agg.actions.some(a => a.status === 'failed') || s.agg.runs.some(r => r.status === 'failed');
            return (
              <li key={s.caseId}>
                <button
                  type="button"
                  onClick={() => navigate(`/cases/${s.caseId}?section=actions`)}
                  className="w-full text-left p-3 rounded border cursor-pointer hover:shadow-md transition-shadow focus-ring"
                  style={{ borderColor: 'var(--sn-line, var(--line))', background: 'transparent' }}
                  data-testid="exec-overview-item"
                >
                  <div className="flex items-center justify-between gap-2">
                    <span className="text-sm font-medium truncate" style={{ color: 'var(--sn-ink, var(--text-primary))' }}>{s.title}</span>
                    {failed
                      ? <span className="text-xs font-medium shrink-0" style={{ color: 'var(--sn-red, var(--color-error))' }}>有失败</span>
                      : <span className="text-xs shrink-0" style={{ color: 'var(--sn-ink-3, var(--text-muted))' }}>正常</span>}
                  </div>
                  <div className="text-xs mt-1.5 num flex gap-3" style={{ color: 'var(--sn-ink-3, var(--text-muted))' }}>
                    <span>待批准 <b style={{ color: pendingApprove > 0 ? 'var(--sn-amber, var(--color-warning))' : undefined }}>{pendingApprove}</b></span>
                    <span>运行中 <b style={{ color: running > 0 ? 'var(--sn-mint, var(--color-success))' : undefined }}>{running}</b></span>
                    <span>待验收 <b style={{ color: pendingAccept > 0 ? 'var(--color-info)' : undefined }}>{pendingAccept}</b></span>
                  </div>
                </button>
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}
