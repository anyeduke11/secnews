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
 *
 * 端点收敛到 api/settings.ts 的 sync 段; 本 hook 只负责 abort 串联 + loading/error 联动。
 */
import { useCallback, useEffect, useRef, useState } from 'react';
import {
  bidirectionalSync,
  clearSyncConfig,
  fetchSyncHistory,
  fetchSyncPreview,
  getSyncStatus,
  pullSync,
  pushSync,
  saveSyncConfig,
  setSyncAuto,
  testSyncConnection,
} from '../api/settings';
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

/** 请求选项 (与 lib/api 的 ApiFetchOptions 兼容子集) */
interface RequestOptions {
  signal?: AbortSignal;
  onLoadingChange?: (loading: boolean) => void;
}

export function useSync() {
  const [status, setStatus] = useState<SyncStatusResponse | null>(null);
  const [history, setHistory] = useState<SyncHistoryItem[]>([]);
  const [preview, setPreview] = useState<SyncBundlePreview | null>(null);
  const [lastResult, setLastResult] = useState<SyncPushResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  // 统一请求外壳: abort 串联 (新请求取消上一次) + loading/error 联动 (与旧实现行为一致)
  const request = useCallback(
    async <T,>(
      run: (options: RequestOptions) => Promise<T>,
      init?: { skipLoading?: boolean },
    ): Promise<T> => {
      if (abortRef.current) abortRef.current.abort();
      const ctrl = new AbortController();
      abortRef.current = ctrl;
      setError(null);
      try {
        return await run({
          signal: ctrl.signal,
          onLoadingChange: init?.skipLoading ? undefined : setLoading,
        });
      } catch (e) {
        // 被新请求 abort 时不污染 error 状态 (与旧实现一致)
        if ((e as Error).name !== 'AbortError') setError((e as Error).message);
        throw e;
      } finally {
        if (abortRef.current === ctrl) abortRef.current = null;
      }
    },
    [],
  );

  // ---- 读 ----
  // 读 —— 出错也写空 status, 避免 SyncPage configured 永远 false
  const fetchStatus = useCallback(async () => {
    try {
      const r = await request<SyncStatusResponse>(opts => getSyncStatus<SyncStatusResponse>(opts));
      setStatus(r);
      return r;
    } catch (e) {
      setStatus({ version: '1.0', status: { configured: false }, recent_history: [] });
      throw e;
    }
  }, [request]);

  // 启动期重试: status 第一次没回来 + history 显示以前配过, 强制再 fetch
  const fetchStatusRetryRef = useRef(0);
  useEffect(() => {
    if (status?.status.configured) return;  // 已 OK
    if (history.length === 0) return;  // 从没配过
    if (fetchStatusRetryRef.current >= 5) return;  // 上限 5 次
    const t = setTimeout(() => {
      fetchStatusRetryRef.current += 1;
      fetchStatus().catch(() => undefined);
    }, 1000);
    return () => clearTimeout(t);
  }, [status, history.length, fetchStatus]);

  const fetchHistory = useCallback(async (limit = 50) => {
    try {
      const r = await request<{ version: string; history: SyncHistoryItem[] }>(opts =>
        fetchSyncHistory<{ version: string; history: SyncHistoryItem[] }>(limit, opts),
      );
      setHistory(r.history);
      return r.history;
    } catch (e) {
      setHistory([]);
      throw e;
    }
  }, [request]);

  const fetchPreview = useCallback(async () => {
    const r = await request<{ version: string; preview: SyncBundlePreview }>(opts =>
      fetchSyncPreview<{ version: string; preview: SyncBundlePreview }>(opts),
    );
    setPreview(r.preview);
    return r.preview;
  }, [request]);

  // ---- 写 ----
  const testConnection = useCallback(async (req: SyncTestRequest) => {
    const r = await request<SyncTestResponse>(opts =>
      testSyncConnection<SyncTestResponse, SyncTestRequest>(req, opts),
    );
    return r;
  }, [request]);

  const upsertConfig = useCallback(async (req: SyncUpsertRequest) => {
    const r = await request<SyncConfigResponse>(opts =>
      saveSyncConfig<SyncConfigResponse, SyncUpsertRequest>(req, opts),
    );
    await fetchStatus();
    return r;
  }, [request, fetchStatus]);

  const deleteConfig = useCallback(async () => {
    await request<{ version: string; deleted: boolean }>(opts =>
      clearSyncConfig<{ version: string; deleted: boolean }>(opts),
    );
    await fetchStatus();
  }, [request, fetchStatus]);

  const setAutoSync = useCallback(async (enabled: boolean) => {
    await request<{ version: string; auto_sync_enabled: boolean }>(opts =>
      setSyncAuto<{ version: string; auto_sync_enabled: boolean }>(enabled, opts),
    );
    await fetchStatus();
  }, [request, fetchStatus]);

  const push = useCallback(async (master_key: string) => {
    const r = await request<SyncPushResponse>(opts => pushSync<SyncPushResponse>(master_key, opts));
    setLastResult(r);
    await fetchStatus();
    await fetchHistory(50);
    return r;
  }, [request, fetchStatus, fetchHistory]);

  const pull = useCallback(async (master_key: string) => {
    const r = await request<SyncPushResponse>(opts => pullSync<SyncPushResponse>(master_key, opts));
    setLastResult(r);
    await fetchStatus();
    await fetchHistory(50);
    return r;
  }, [request, fetchStatus, fetchHistory]);

  const bidirectional = useCallback(async (master_key: string) => {
    const r = await request<SyncPushResponse>(opts =>
      bidirectionalSync<SyncPushResponse>(master_key, opts),
    );
    setLastResult(r);
    await fetchStatus();
    await fetchHistory(50);
    return r;
  }, [request, fetchStatus, fetchHistory]);

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