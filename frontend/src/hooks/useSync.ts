/**
 * Phase 42 跨端配置同步 hook (WebDAV)。
 *
 * 状态:
 *   - status: 当前 sync_configs + status 摘要 + recent history
 *   - history: 完整 history 列表
 *   - preview: 本机 bundle 字段数预览
 *   - lastResult: 最近一次 push/pull/bidirectional 结果
 *   - loading: 任一请求进行中
 *   - error: 最近一次错误
 *
 * 操作:
 *   - fetchStatus()  /  fetchHistory()  /  fetchPreview()
 *   - testConnection(payload)  →  返回 ok + message (不抛错)
 *   - upsertConfig(payload)  /  deleteConfig()
 *   - setAutoSync(enabled)
 *   - push(masterKey)  /  pull(masterKey)  /  bidirectional(masterKey)
 *
 * 错误: 4xx/5xx 抛到 .catch, 调用方负责处理 (UI 一般用 toast).
 */
import { useCallback, useEffect, useRef, useState } from 'react';
import type {
  SyncBundlePreview,
  SyncConfigResponse,
  SyncHistoryItem,
  SyncPushResponse,
  SyncStatusResponse,
  SyncTestRequest,
  SyncTestResponse,
  SyncUpsertRequest,
} from '../types';

export function useSync() {
  const [status, setStatus] = useState<SyncStatusResponse | null>(null);
  const [history, setHistory] = useState<SyncHistoryItem[]>([]);
  const [preview, setPreview] = useState<SyncBundlePreview | null>(null);
  const [lastResult, setLastResult] = useState<SyncPushResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  // 通用 fetch 包装
  const apiFetch = useCallback(async <T,>(
    url: string,
    init?: RequestInit & { skipLoading?: boolean },
  ): Promise<T> => {
    if (abortRef.current) abortRef.current.abort();
    const ctrl = new AbortController();
    abortRef.current = ctrl;
    if (!init?.skipLoading) setLoading(true);
    setError(null);
    try {
      const resp = await fetch(url, {
        ...init,
        signal: ctrl.signal,
        headers: {
          'Content-Type': 'application/json',
          ...(init?.headers || {}),
        },
      });
      if (!resp.ok) {
        let detail: any = null;
        try { detail = await resp.json(); } catch { /* ignore */ }
        const msg = (detail?.detail?.message || detail?.detail || resp.statusText || `HTTP ${resp.status}`) as string;
        setError(msg);
        throw new Error(msg);
      }
      return (await resp.json()) as T;
    } finally {
      if (abortRef.current === ctrl) abortRef.current = null;
      if (!init?.skipLoading) setLoading(false);
    }
  }, []);

  // ---- 读 ----
  // 读 —— 出错也写空 status, 避免 SyncPage configured 永远 false
  const fetchStatus = useCallback(async () => {
    try {
      const r = await apiFetch<SyncStatusResponse>('/api/sync/status');
      setStatus(r);
      return r;
    } catch (e) {
      setStatus({ version: '1.0', status: { configured: false }, recent_history: [] });
      throw e;
    }
  }, [apiFetch]);

  const fetchHistory = useCallback(async (limit = 50) => {
    try {
      const r = await apiFetch<{ version: string; history: SyncHistoryItem[] }>(
        `/api/sync/history?limit=${limit}`,
      );
      setHistory(r.history);
      return r.history;
    } catch (e) {
      setHistory([]);
      throw e;
    }
  }, [apiFetch]);

  const fetchPreview = useCallback(async () => {
    const r = await apiFetch<{ version: string; preview: SyncBundlePreview }>(
      '/api/sync/bundle/preview',
    );
    setPreview(r.preview);
    return r.preview;
  }, [apiFetch]);

  // ---- 写 ----
  const testConnection = useCallback(async (req: SyncTestRequest) => {
    const r = await apiFetch<SyncTestResponse>('/api/sync/test', {
      method: 'POST',
      body: JSON.stringify(req),
    });
    return r;
  }, [apiFetch]);

  const upsertConfig = useCallback(async (req: SyncUpsertRequest) => {
    const r = await apiFetch<SyncConfigResponse>('/api/sync/config', {
      method: 'POST',
      body: JSON.stringify(req),
    });
    await fetchStatus();
    return r;
  }, [apiFetch, fetchStatus]);

  const deleteConfig = useCallback(async () => {
    await apiFetch<{ version: string; deleted: boolean }>('/api/sync/config', {
      method: 'DELETE',
    });
    await fetchStatus();
  }, [apiFetch, fetchStatus]);

  const setAutoSync = useCallback(async (enabled: boolean) => {
    await apiFetch<{ version: string; auto_sync_enabled: boolean }>('/api/sync/auto', {
      method: 'POST',
      body: JSON.stringify({ enabled }),
    });
    await fetchStatus();
  }, [apiFetch, fetchStatus]);

  const push = useCallback(async (master_key: string) => {
    const r = await apiFetch<SyncPushResponse>('/api/sync/push', {
      method: 'POST',
      body: JSON.stringify({ master_key }),
    });
    setLastResult(r);
    await fetchStatus();
    await fetchHistory(50);
    return r;
  }, [apiFetch, fetchStatus, fetchHistory]);

  const pull = useCallback(async (master_key: string) => {
    const r = await apiFetch<SyncPushResponse>('/api/sync/pull', {
      method: 'POST',
      body: JSON.stringify({ master_key }),
    });
    setLastResult(r);
    await fetchStatus();
    await fetchHistory(50);
    return r;
  }, [apiFetch, fetchStatus, fetchHistory]);

  const bidirectional = useCallback(async (master_key: string) => {
    const r = await apiFetch<SyncPushResponse>('/api/sync/bidirectional', {
      method: 'POST',
      body: JSON.stringify({ master_key }),
    });
    setLastResult(r);
    await fetchStatus();
    await fetchHistory(50);
    return r;
  }, [apiFetch, fetchStatus, fetchHistory]);

  // 启动时拉一次 status
  useEffect(() => {
    fetchStatus().catch(() => undefined);
    fetchHistory(20).catch(() => undefined);
    return () => {
      if (abortRef.current) abortRef.current.abort();
    };
  }, [fetchStatus, fetchHistory]);

  return {
    status,
    history,
    preview,
    lastResult,
    loading,
    error,
    fetchStatus,
    fetchHistory,
    fetchPreview,
    testConnection,
    upsertConfig,
    deleteConfig,
    setAutoSync,
    push,
    pull,
    bidirectional,
  };
}
