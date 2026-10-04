/**
 * RejectionReplay — 质量门禁拒收回放区块 (v0.8.6 P1-5, 审计 F1-3)。
 *
 * 验收: "任取一条拒绝，可在 UI 看到原文与原因" — strict 拒收标记行
 * (gate_name=pipeline) LEFT JOIN raw_items 原文; raw 缺失诚实显示
 * "原文未留存", 不伪造。挂 ObservabilityTab (资讯观测域, 零新路由)。
 */
import { useCallback, useEffect, useState } from 'react';
import {
  getQualityRejections,
  type QualityRejection,
} from '../../../api/secnews';

function RejectionRow({ r }: { r: QualityRejection }) {
  return (
    <li
      className="p-2.5 rounded border flex flex-col gap-1"
      style={{ borderColor: 'var(--sn-line, var(--line))' }}
      data-testid="rejection-row"
    >
      <div className="flex flex-wrap items-center gap-2">
        <span
          className="text-xs font-bold"
          style={{ color: 'var(--sn-red, var(--color-error))' }}
        >
          拒收
        </span>
        <span className="text-xs num" style={{ color: 'var(--sn-ink-3, var(--text-muted))' }}>
          {r.checked_at.slice(0, 16).replace('T', ' ')}
        </span>
        <span className="text-xs num" style={{ color: 'var(--sn-ink-3, var(--text-muted))' }}>
          {r.item_id.slice(0, 18)}
        </span>
        {r.flags.length > 0 && (
          <span className="text-xs num" style={{ color: 'var(--sn-amber, var(--color-warning))' }}>
            {r.flags.join(' · ')}
          </span>
        )}
      </div>
      <p className="text-xs break-words" style={{ color: 'var(--sn-ink, var(--text-primary))' }}>
        {r.reason || '(无原因记录)'}
      </p>
      {r.raw ? (
        <div className="text-xs pl-2 border-l-2" style={{ borderColor: 'var(--sn-line, var(--line))' }}>
          {r.raw.url ? (
            <a
              href={r.raw.url}
              target="_blank"
              rel="noopener noreferrer"
              className="font-medium underline-offset-2 hover:underline"
              style={{ color: 'var(--color-info)' }}
            >
              {r.raw.title || r.raw.url}
            </a>
          ) : (
            <span style={{ color: 'var(--sn-ink, var(--text-primary))' }}>
              {r.raw.title || '(无标题)'}
            </span>
          )}
          {r.raw.summary && (
            <p className="line-clamp-2" style={{ color: 'var(--sn-ink-3, var(--text-muted))' }}>
              {r.raw.summary.slice(0, 160)}
            </p>
          )}
        </div>
      ) : (
        <p className="text-xs" style={{ color: 'var(--sn-ink-3, var(--text-muted))' }}>
          原文未留存（raw_items 无此条）
        </p>
      )}
    </li>
  );
}

export function RejectionReplay() {
  const [items, setItems] = useState<QualityRejection[] | null>(null);
  const [total, setTotal] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [expanded, setExpanded] = useState(false);

  const load = useCallback(async () => {
    setError(null);
    try {
      const body = await getQualityRejections(168, expanded ? 50 : 8);
      setItems(body.items);
      setTotal(body.total);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }, [expanded]);

  useEffect(() => { void load(); }, [load]);

  return (
    <section
      aria-label="质量门禁拒收回放"
      data-testid="rejection-replay"
      className="p-4 rounded border"
      style={{ borderColor: 'var(--sn-line, var(--line))', background: 'var(--bg-card, transparent)' }}
    >
      <header className="flex items-center gap-2 mb-2">
        <span
          className="text-xs font-bold uppercase tracking-wider num"
          style={{ color: 'var(--sn-red, var(--color-error))' }}
        >
          拒收回放
        </span>
        <span className="text-xs num" style={{ color: 'var(--sn-ink-3, var(--text-muted))' }}>
          近 7 天拒收 {total} 条 · 原文与原因可回溯
        </span>
        <button
          type="button"
          className="ml-auto text-xs num px-2 py-0.5 rounded focus-ring"
          style={{ border: '1px solid var(--sn-line, var(--line))', color: 'var(--sn-ink-3, var(--text-muted))' }}
          onClick={() => { void load(); }}
        >
          刷新
        </button>
      </header>

      {error && (
        <p role="alert" className="text-sm" style={{ color: 'var(--color-error)' }}>
          拒收回放不可用: {error}
        </p>
      )}
      {!error && items === null && (
        <p className="text-sm" style={{ color: 'var(--sn-ink-3, var(--text-muted))' }}>加载中…</p>
      )}
      {items !== null && items.length === 0 && (
        <p className="text-sm" style={{ color: 'var(--sn-ink-3, var(--text-muted))' }}>
          窗口内无拒收记录（strict 门禁全通过）
        </p>
      )}
      {items !== null && items.length > 0 && (
        <>
          <ul className="flex flex-col gap-2">
            {items.map(r => <RejectionRow key={`${r.item_id}-${r.checked_at}`} r={r} />)}
          </ul>
          {total > items.length && (
            <button
              type="button"
              className="mt-2 text-xs num px-2 py-1 rounded focus-ring"
              style={{ border: '1px solid var(--sn-line, var(--line))', color: 'var(--sn-ink-2)' }}
              onClick={() => setExpanded(true)}
              data-testid="rejection-more-btn"
            >
              展开更多（共 {total} 条）
            </button>
          )}
        </>
      )}
    </section>
  );
}
