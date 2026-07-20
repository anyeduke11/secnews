// frontend/src/hooks/useCodegardenServices.ts
import { useState, useEffect, useCallback, useRef } from 'react';
import {
  CgService,
  CgServiceListResponse,
  CgServiceTopology,
  ServiceScanResponse,
  ServiceRuntime,
  ServiceStatus,
  ServiceType,
} from '../types/codegarden';

export interface UseCodegardenServicesReturn {
  items: CgService[];
  total: number;
  loading: boolean;
  error: string | null;
  runtime: ServiceRuntime | 'all';
  status: ServiceStatus | 'all';
  serviceType: ServiceType | 'all';
  keyword: string;
  setRuntime: (v: ServiceRuntime | 'all') => void;
  setStatus: (v: ServiceStatus | 'all') => void;
  setServiceType: (v: ServiceType | 'all') => void;
  setKeyword: (k: string) => void;
  refresh: () => Promise<void>;
  scan: () => Promise<ServiceScanResponse>;
  restart: (id: string) => Promise<{ task_id: number }>;
  getLogs: (id: string, tail?: number) => Promise<string>;
  getMetrics: (id: string) => Promise<Record<string, unknown>>;
  getTopology: () => Promise<CgServiceTopology>;
}

export function useCodegardenServices(): UseCodegardenServicesReturn {
  const [items, setItems] = useState<CgService[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [runtime, setRuntime] = useState<ServiceRuntime | 'all'>('all');
  const [status, setStatus] = useState<ServiceStatus | 'all'>('all');
  const [serviceType, setServiceType] = useState<ServiceType | 'all'>('all');
  const [keyword, setKeyword] = useState('');

  const abortRef = useRef<AbortController | null>(null);

  const fetchList = useCallback(async () => {
    if (abortRef.current) abortRef.current.abort();
    const ctrl = new AbortController();
    abortRef.current = ctrl;
    setLoading(true);
    setError(null);
    try {
      const params = new URLSearchParams({ limit: '500' });
      if (runtime !== 'all') params.set('runtime', runtime);
      if (status !== 'all') params.set('status', status);
      if (serviceType !== 'all') params.set('type', serviceType);
      if (keyword.trim()) params.set('keyword', keyword.trim());

      const r = await fetch(`/api/codegarden/services?${params}`, {
        signal: ctrl.signal,
        headers: { Accept: 'application/json' },
      });
      if (!r.ok) throw new Error(`请求失败 (${r.status})`);
      const data: CgServiceListResponse = await r.json();
      setItems(data.items || []);
      setTotal(data.total || 0);
    } catch (e: any) {
      if (e?.name === 'AbortError') return;
      setError(e?.message || '加载失败');
    } finally {
      if (abortRef.current === ctrl) setLoading(false);
    }
  }, [runtime, status, serviceType, keyword]);

  useEffect(() => {
    fetchList();
    return () => { if (abortRef.current) abortRef.current.abort(); };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    const t = setTimeout(() => fetchList(), 250);
    return () => clearTimeout(t);
  }, [fetchList]);

  const refresh = useCallback(async () => { await fetchList(); }, [fetchList]);

  const scan = useCallback(async (): Promise<ServiceScanResponse> => {
    const r = await fetch('/api/codegarden/services/scan', { method: 'POST' });
    if (!r.ok) throw new Error(`扫描失败 (${r.status})`);
    const data: ServiceScanResponse = await r.json();
    await fetchList();
    return data;
  }, [fetchList]);

  const restart = useCallback(async (id: string): Promise<{ task_id: number }> => {
    const r = await fetch(`/api/codegarden/services/${id}/restart`, { method: 'POST' });
    if (!r.ok) throw new Error(`重启失败 (${r.status})`);
    const data = await r.json();
    return { task_id: data.task_id };
  }, []);

  const getLogs = useCallback(async (id: string, tail = 200): Promise<string> => {
    const r = await fetch(`/api/codegarden/services/${id}/logs?tail=${tail}`);
    if (!r.ok) throw new Error(`日志获取失败 (${r.status})`);
    const data = await r.json();
    return data.logs || '';
  }, []);

  const getMetrics = useCallback(async (id: string): Promise<Record<string, unknown>> => {
    const r = await fetch(`/api/codegarden/services/${id}/metrics`);
    if (!r.ok) throw new Error(`指标获取失败 (${r.status})`);
    return await r.json();
  }, []);

  const getTopology = useCallback(async (): Promise<CgServiceTopology> => {
    const r = await fetch('/api/codegarden/services/topology');
    if (!r.ok) throw new Error(`拓扑图获取失败 (${r.status})`);
    return await r.json();
  }, []);

  return {
    items, total, loading, error,
    runtime, status, serviceType, keyword,
    setRuntime, setStatus, setServiceType, setKeyword,
    refresh, scan, restart, getLogs, getMetrics, getTopology,
  };
}
