/**
 * SignalPanelCompact — 资讯右栏「今日 Signal 摘要」(R-15)
 *
 * 与完整面板同一数据源 (listSignals), 但只看今日 3 条 + 只读展示 + 去行动入口, 不含立项动作。
 *
 * D7 收口 (2026-11-18): 从 SignalPanel 拆成独立模块 ——
 * 右栏摘要在首屏同步加载, 而完整「受管信号」面板位于主列之后 (首屏之下) 改为按需加载;
 * 两者同处一个模块时, 首屏会被完整面板 (立项动作 + Subject 抽屉 + 面板外壳) 一起拖进包体。
 */
import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { listSignals, type V1Signal } from '../../../api/v1';

export function SignalPanelCompact() {
  const navigate = useNavigate();
  const [signals, setSignals] = useState<V1Signal[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    listSignals({ days: 1, limit: 3 })
      .then(r => { if (!cancelled) setSignals(r.items || []); })
      .catch(e => { if (!cancelled) { setError(e instanceof Error ? e.message : String(e)); setSignals([]); } })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, []);

  return (
    <section className="rail-mod" aria-label="今日 Signal 摘要" data-testid="rail-signal-summary">
      <h3>
        今日 SIGNAL
        <span className="rail-note">{loading ? '…' : error ? '未就绪' : `${signals.length} 条`}</span>
      </h3>
      {error && <p className="rail-note" style={{ margin: '8px 0 0' }}>信号接口未就绪 (unavailable)</p>}
      {!error && !loading && signals.length === 0 && (
        <p className="rail-note" style={{ margin: '8px 0 0' }}>今日暂无受管信号</p>
      )}
      {!error && signals.length > 0 && (
        <ul style={{ listStyle: 'none', padding: 0, margin: 0 }}>
          {signals.map(s => (
            <li key={s.id} style={{ padding: '9px 0', borderBottom: '1px solid var(--sn-line)' }}>
              <div style={{ fontSize: 12, lineHeight: 1.45, color: 'var(--sn-ink)' }}>{s.summary}</div>
              <div style={{ fontSize: 10.5, fontFamily: 'var(--sn-mono)', color: 'var(--sn-ink-3)', marginTop: 3 }}>
                {s.occurred_at} · {s.confidence} · {s.subject_name || s.subject_id}
              </div>
            </li>
          ))}
        </ul>
      )}
      <button
        type="button"
        onClick={() => navigate('/action')}
        aria-label="进入行动指挥台查看全部信号"
        style={{ marginTop: 10, padding: 0, background: 'none', border: 'none', cursor: 'pointer', fontSize: 11, color: 'var(--sn-mint)' }}
      >
        去行动 ›
      </button>
    </section>
  );
}
