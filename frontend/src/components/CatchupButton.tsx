// frontend/src/components/CatchupButton.tsx
// v1.8 Phase 8 — 追抓资讯按钮 (manual trigger + abort + status polling)
//
// v2 精简: 合并触发/中止/进度为一颗按钮, 无多余 span.
//
// 行为
// ----
// 1. 挂载时 GET /api/catchup/status → 拿 current_manual_run_id + recent
// 2. 点击"追抓"按钮 → POST /api/catchup/run (since=24h前, max_per_source=20)
// 3. running 时每 3s 轮询 status, 按钮文字变为进度; 再点即中止
// 4. 终态后停止轮询, 显示 toast

import { useCallback, useEffect, useRef, useState } from 'react';

interface CatchupRun {
  id: number;
  mode: string;
  status: string;
  started_at: string;
  finished_at: string | null;
  items_ingested: number;
  items_skipped: number;
  sources_attempted: number;
  sources_succeeded: number;
  sources_skipped: number;
  error_msg: string | null;
  duration_s: number;
  categories: string[];
}

interface CatchupStatus {
  current_running: CatchupRun | null;
  current_manual_run_id: number | null;
  recent: CatchupRun[];
  last_orphan_recovery_at: string | null;
  total_recent: number;
}

interface Toast {
  msg: string;
  ok: boolean;
}

const POLL_INTERVAL_MS = 3000;

export function CatchupButton() {
  const [status, setStatus] = useState<CatchupStatus | null>(null);
  const [busy, setBusy] = useState(false);
  const [toast, setToast] = useState<Toast | null>(null);
  const pollTimerRef = useRef<number | null>(null);

  const flashToast = useCallback((msg: string, ok: boolean) => {
    setToast({ msg, ok });
    setTimeout(() => setToast(null), 3000);
  }, []);

  // Fetch status
  const fetchStatus = useCallback(async (): Promise<CatchupStatus | null> => {
    try {
      const r = await fetch('/api/catchup/status?limit=5');
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      return (await r.json()) as CatchupStatus;
    } catch (e) {
      console.warn('catchup status fetch failed:', e);
      return null;
    }
  }, []);

  // Start polling when there's a running run
  useEffect(() => {
    const isRunning = status?.current_running != null;
    if (isRunning && pollTimerRef.current === null) {
      pollTimerRef.current = window.setInterval(async () => {
        const s = await fetchStatus();
        if (s) {
          setStatus(s);
          if (s.current_running == null) {
            if (pollTimerRef.current != null) {
              window.clearInterval(pollTimerRef.current);
              pollTimerRef.current = null;
            }
            const last = s.recent?.[0];
            if (last) {
              if (last.status === 'success') {
                flashToast(
                  `✓ 追抓完成: ${last.items_ingested} 条 (${last.sources_succeeded}/${last.sources_attempted} 源)`,
                  true,
                );
              } else if (last.status === 'partial') {
                flashToast(
                  `△ 追抓部分成功: ${last.items_ingested} 条 (${last.sources_succeeded}/${last.sources_attempted} 源)`,
                  true,
                );
              } else if (last.status === 'aborted') {
                flashToast('追抓已中止', false);
              } else if (last.status === 'failed') {
                flashToast(
                  `✗ 追抓失败: ${last.error_msg?.slice(0, 60) || '未知错误'}`,
                  false,
                );
              }
            }
          }
        }
      }, POLL_INTERVAL_MS);
    }
    return () => {
      if (pollTimerRef.current != null && !isRunning) {
        window.clearInterval(pollTimerRef.current);
        pollTimerRef.current = null;
      }
    };
  }, [status?.current_running, fetchStatus, flashToast]);

  // Mount: fetch status once + re-fetch when tab becomes visible
  useEffect(() => {
    let cancelled = false;
    const refresh = async () => {
      const s = await fetchStatus();
      if (!cancelled) setStatus(s);
    };
    refresh();
    const onVisible = () => {
      if (document.visibilityState === 'visible') refresh();
    };
    document.addEventListener('visibilitychange', onVisible);
    window.addEventListener('focus', refresh);
    return () => {
      cancelled = true;
      document.removeEventListener('visibilitychange', onVisible);
      window.removeEventListener('focus', refresh);
      if (pollTimerRef.current != null) {
        window.clearInterval(pollTimerRef.current);
        pollTimerRef.current = null;
      }
    };
  }, [fetchStatus]);

  // Trigger
  const handleTrigger = async () => {
    if (busy) return;
    if (status?.current_running) {
      flashToast('已有追抓在跑, 请先中止或等待完成', false);
      return;
    }
    setBusy(true);
    try {
      const since = new Date(Date.now() - 24 * 3600 * 1000).toISOString();
      const r = await fetch('/api/catchup/run', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          since,
          until: null,
          categories: [],
          max_per_source: 20,
        }),
      });
      if (r.status === 409) {
        flashToast('已有 manual 追抓在跑', false);
        return;
      }
      if (!r.ok) {
        const errBody = await r.json().catch(() => ({}));
        const msg = errBody?.detail?.message || `HTTP ${r.status}`;
        throw new Error(msg);
      }
      const data = await r.json();
      flashToast(`追抓已触发 (run_id=${data.run_id})`, true);
      const s = await fetchStatus();
      if (s) setStatus(s);
    } catch (e: any) {
      flashToast(`✗ 触发失败: ${e?.message || String(e)}`, false);
    } finally {
      setBusy(false);
    }
  };

  // Abort
  const handleAbort = async () => {
    if (busy) return;
    setBusy(true);
    try {
      const r = await fetch('/api/catchup/abort', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({}),
      });
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      const data = await r.json();
      if (data.ok) {
        flashToast(`已中止 run_id=${data.aborted_run_id}`, true);
      } else {
        flashToast('当前无 manual 在跑', false);
      }
      const s = await fetchStatus();
      if (s) setStatus(s);
    } catch (e: any) {
      flashToast(`✗ 中止失败: ${e?.message || String(e)}`, false);
    } finally {
      setBusy(false);
    }
  };

  const running = status?.current_running;
  const isManualRunning = running?.mode === 'manual';

  // 运行中: 单颗按钮内含进度 + 可点击中止
  if (running && isManualRunning) {
    return (
      <div className="inline-flex items-center gap-1">
        <button
          onClick={handleAbort}
          disabled={busy}
          data-testid="catchup-trigger"
          className="btn-ghost px-2 py-1.5 text-[11px] whitespace-nowrap"
          style={{
            color: 'var(--color-error)',
            opacity: busy ? 0.5 : 1,
            cursor: busy ? 'not-allowed' : undefined,
          }}
          title="点击中止追抓"
          aria-label="追抓中，点击中止"
        >
          <span aria-hidden className="inline-block mr-0.5" style={{ color: 'var(--accent)' }}>⏳</span>
          #{running.id} {running.sources_succeeded}/{running.sources_attempted} 源
          {running.sources_skipped > 0 && ` · 跳${running.sources_skipped}`}
          {running.items_ingested > 0 && ` · ${running.items_ingested} 条`}
        </button>
        {toast && (
          <span className="text-[10px] px-1.5 py-0.5 rounded-[var(--radius-sm)]" style={{ backgroundColor: 'var(--bg-hover)', color: toast.ok ? 'var(--color-success)' : 'var(--color-error)' }}>
            {toast.msg}
          </span>
        )}
      </div>
    );
  }

  // 空闲: 图标按钮
  return (
    <div className="inline-flex items-center gap-1">
      <button
        onClick={handleTrigger}
        disabled={busy}
        data-testid="catchup-trigger"
        className="nav-btn"
        style={{
          color: 'var(--accent)',
          opacity: busy ? 0.5 : 1,
          cursor: busy ? 'not-allowed' : undefined,
        }}
        title="追抓 24h 内的资讯"
        aria-label="追抓"
      >
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
          <circle cx="12" cy="12" r="10" />
          <circle cx="12" cy="12" r="3" />
        </svg>
      </button>
      {toast && (
        <span
          data-testid="catchup-toast"
          className="text-[10px] px-1.5 py-0.5 rounded-[var(--radius-sm)]"
          style={{ backgroundColor: 'var(--bg-hover)', color: toast.ok ? 'var(--color-success)' : 'var(--color-error)' }}
        >
          {toast.msg}
        </span>
      )}
    </div>
  );
}

export default CatchupButton;
