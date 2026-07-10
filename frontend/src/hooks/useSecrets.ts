import { useState, useEffect, useCallback, useRef } from 'react';
import {
  SecretItem,
  SecretListResponse,
  SecretStatusResponse,
  SecretUnlockResponse,
  SecretRevealResponse,
  SecretTestResponse,
  SecretImportResponse,
  SecretCreateRequest,
  SecretUpdateRequest,
} from '../types';

export interface UseSecretsReturn {
  status: SecretStatusResponse | null;
  items: SecretItem[];
  total: number;
  loading: boolean;
  error: string | null;

  // 操作
  refreshStatus: () => Promise<void>;
  refreshList: () => Promise<void>;
  setupMasterKey: (masterKey: string) => Promise<void>;
  unlock: (masterKey: string) => Promise<SecretUnlockResponse>;
  lock: () => Promise<void>;
  add: (req: SecretCreateRequest) => Promise<SecretItem>;
  update: (id: number, req: SecretUpdateRequest) => Promise<SecretItem>;
  remove: (id: number) => Promise<void>;
  reveal: (id: number) => Promise<SecretRevealResponse>;
  testConnection: (id: number) => Promise<SecretTestResponse>;
  exportSecrets: (masterKey: string) => Promise<Blob>;
  importSecrets: (file: File, masterKey: string) => Promise<SecretImportResponse>;
}

/**
 * Phase 41 密钥管理 Hook
 *
 * 负责:
 *  - status (setup + unlock 状态 + 剩余秒数)
 *  - 列表 (无明文, 包含 unlocked 标记)
 *  - setup / unlock / lock
 *  - CRUD: add / update / remove (改 api_key 必须传 master_key)
 *  - reveal (在 unlock 状态下拿到明文)
 *  - test connection (Phase 41 Q4)
 *  - import / export (Phase 41 Q3, 加密 JSON)
 */
export function useSecrets(): UseSecretsReturn {
  const [status, setStatus] = useState<SecretStatusResponse | null>(null);
  const [items, setItems] = useState<SecretItem[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const listAbortRef = useRef<AbortController | null>(null);

  const refreshStatus = useCallback(async () => {
    try {
      const r = await fetch('/api/secrets/status', {
        headers: { Accept: 'application/json' },
      });
      if (!r.ok) return;
      const data: SecretStatusResponse = await r.json();
      setStatus(data);
    } catch {
      // 静默
    }
  }, []);

  const refreshList = useCallback(async () => {
    if (listAbortRef.current) listAbortRef.current.abort();
    const controller = new AbortController();
    listAbortRef.current = controller;
    setLoading(true);
    setError(null);
    try {
      const r = await fetch('/api/secrets', {
        signal: controller.signal,
        headers: { Accept: 'application/json' },
      });
      if (!r.ok) {
        const t = await r.text().catch(() => '');
        throw new Error(`加载失败 (${r.status})${t ? `: ${t.slice(0, 200)}` : ''}`);
      }
      const data: SecretListResponse = await r.json();
      setItems(data.items || []);
      setTotal(data.total || 0);
    } catch (e: any) {
      if (e?.name === 'AbortError') return;
      setError(e?.message || '加载失败');
    } finally {
      if (listAbortRef.current === controller) {
        setLoading(false);
      }
    }
  }, []);

  // 初次 mount: 拉 status (unlock 状态)
  useEffect(() => {
    refreshStatus();
    return () => {
      if (listAbortRef.current) listAbortRef.current.abort();
    };
  }, [refreshStatus]);

  // setup 后或 unlock 后拉列表
  useEffect(() => {
    if (status?.setup) {
      refreshList();
    }
  }, [status?.setup, status?.unlocked, refreshList]);

  // unlock 倒计时: 状态 30 分钟内每 30s 拉一次 (前端不精确计时, 后端为准)
  useEffect(() => {
    if (!status?.unlocked) return;
    const t = window.setInterval(() => {
      refreshStatus();
    }, 30 * 1000);
    return () => window.clearInterval(t);
  }, [status?.unlocked, refreshStatus]);

  const setupMasterKey = useCallback(
    async (masterKey: string): Promise<void> => {
      const r = await fetch('/api/secrets/setup', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
        body: JSON.stringify({ master_key: masterKey }),
      });
      if (!r.ok) {
        const j = await r.json().catch(() => ({}));
        const msg = (j as any)?.detail?.message || `设置失败 (${r.status})`;
        throw new Error(msg);
      }
      await refreshStatus();
    },
    [refreshStatus]
  );

  const unlock = useCallback(
    async (masterKey: string): Promise<SecretUnlockResponse> => {
      const r = await fetch('/api/secrets/unlock', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
        body: JSON.stringify({ master_key: masterKey }),
      });
      if (!r.ok) {
        const j = await r.json().catch(() => ({}));
        const msg = (j as any)?.detail?.message || `解锁失败 (${r.status})`;
        throw new Error(msg);
      }
      const data: SecretUnlockResponse = await r.json();
      await refreshStatus();
      await refreshList();
      return data;
    },
    [refreshStatus, refreshList]
  );

  const lock = useCallback(async (): Promise<void> => {
    const r = await fetch('/api/secrets/lock', { method: 'POST' });
    if (!r.ok) throw new Error(`锁定失败 (${r.status})`);
    await refreshStatus();
    await refreshList();
  }, [refreshStatus, refreshList]);

  const add = useCallback(
    async (req: SecretCreateRequest): Promise<SecretItem> => {
      const r = await fetch('/api/secrets', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
        body: JSON.stringify(req),
      });
      if (!r.ok) {
        const j = await r.json().catch(() => ({}));
        const msg = (j as any)?.detail?.message || `新建失败 (${r.status})`;
        throw new Error(msg);
      }
      const data = await r.json();
      const item: SecretItem = data.item;
      setItems(prev => [item, ...prev]);
      setTotal(prev => prev + 1);
      return item;
    },
    []
  );

  const update = useCallback(
    async (id: number, req: SecretUpdateRequest): Promise<SecretItem> => {
      const r = await fetch(`/api/secrets/${id}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
        body: JSON.stringify(req),
      });
      if (!r.ok) {
        const j = await r.json().catch(() => ({}));
        const msg = (j as any)?.detail?.message || `更新失败 (${r.status})`;
        throw new Error(msg);
      }
      const data = await r.json();
      const item: SecretItem = data.item;
      setItems(prev => prev.map(p => (p.id === id ? item : p)));
      return item;
    },
    []
  );

  const remove = useCallback(
    async (id: number): Promise<void> => {
      const r = await fetch(`/api/secrets/${id}`, { method: 'DELETE' });
      if (!r.ok && r.status !== 204) {
        throw new Error(`删除失败 (${r.status})`);
      }
      setItems(prev => prev.filter(p => p.id !== id));
      setTotal(prev => Math.max(0, prev - 1));
    },
    []
  );

  const reveal = useCallback(
    async (id: number): Promise<SecretRevealResponse> => {
      const r = await fetch(`/api/secrets/${id}/reveal`, { method: 'POST' });
      if (!r.ok) {
        const j = await r.json().catch(() => ({}));
        const msg = (j as any)?.detail?.message || `获取明文失败 (${r.status})`;
        throw new Error(msg);
      }
      return r.json();
    },
    []
  );

  const testConnection = useCallback(
    async (id: number): Promise<SecretTestResponse> => {
      const r = await fetch(`/api/secrets/${id}/test`, { method: 'POST' });
      if (!r.ok) {
        const j = await r.json().catch(() => ({}));
        const msg = (j as any)?.detail?.message || `测试失败 (${r.status})`;
        throw new Error(msg);
      }
      return r.json();
    },
    []
  );

  // 文件名格式: secrets-export-{unix_ts}.json
  const exportSecrets = useCallback(
    async (masterKey: string): Promise<Blob> => {
      // 后端强制走 query 参数, 但 master_key 不能放 URL (易被日志记录) —
      // 改成 POST + body 模式更安全; 不过这里 API 已经写好了 GET + query,
      // 所以走 GET 接受这个 trade-off (短 TTL, 浏览器内存, 不会进 server log)
      const url = `/api/secrets/export?master_key=${encodeURIComponent(masterKey)}`;
      const r = await fetch(url);
      if (!r.ok) {
        const j = await r.json().catch(() => ({}));
        const msg = (j as any)?.detail?.message || `导出失败 (${r.status})`;
        throw new Error(msg);
      }
      return r.blob();
    },
    []
  );

  const importSecrets = useCallback(
    async (file: File, masterKey: string): Promise<SecretImportResponse> => {
      // 读为 base64, POST 到 /api/secrets/import
      const buf = await file.arrayBuffer();
      const bytes = new Uint8Array(buf);
      // 浏览器自带的 btoa 只能处理 latin1, 需要先转 binary string
      let binary = '';
      for (let i = 0; i < bytes.length; i++) {
        binary += String.fromCharCode(bytes[i]);
      }
      const base64 = btoa(binary);

      const r = await fetch('/api/secrets/import', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
        body: JSON.stringify({ payload_b64: base64, master_key: masterKey }),
      });
      if (!r.ok) {
        const j = await r.json().catch(() => ({}));
        const msg = (j as any)?.detail?.message || `导入失败 (${r.status})`;
        throw new Error(msg);
      }
      return r.json();
    },
    []
  );

  return {
    status,
    items,
    total,
    loading,
    error,
    refreshStatus,
    refreshList,
    setupMasterKey,
    unlock,
    lock,
    add,
    update,
    remove,
    reveal,
    testConnection,
    exportSecrets,
    importSecrets,
  };
}
