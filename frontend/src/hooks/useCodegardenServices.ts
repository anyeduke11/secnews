// frontend/src/hooks/useCodegardenServices.ts
import { useState, useEffect, useCallback, useRef } from 'react';
import {
  CgService,
  CgServiceTopology,
  ServiceScanResponse,
  ServiceRuntime,
  ServiceStatus,
  ServiceType,
} from '../types/codegarden';
import {
  listServices,
  scanServices,
  restartService,
  getServiceLogs,
  getServiceMetrics,
  getServiceTopology,
} from '../api/codegarden';

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
      const data = await listServices(
        {
          limit: 500,
          runtime: runtime !== 'all' ? runtime : undefined,
          status: status !== 'all' ? status : undefined,
          type: serviceType !== 'all' ? serviceType : undefined,
          keyword: keyword.trim() || undefined,
        },
        { signal: ctrl.signal },
      );
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
    const data = await scanServices();
    await fetchList();
    return data;
  }, [fetchList]);

  const restart = useCallback(async (id: string): Promise<{ task_id: number }> => {
    const data = await restartService(id);
    return { task_id: data.task_id };
  }, []);

  const getLogs = useCallback(async (id: string, tail = 200): Promise<string> => {
    const data = await getServiceLogs(id, tail);
    return data.logs || '';
  }, []);

  const getMetrics = useCallback(async (id: string): Promise<Record<string, unknown>> => {
    return await getServiceMetrics(id);
  }, []);

  const getTopology = useCallback(async (): Promise<CgServiceTopology> => {
    return await getServiceTopology();
  }, []);

  return {
    items, total, loading, error,
    runtime, status, serviceType, keyword,
    setRuntime, setStatus, setServiceType, setKeyword,
    refresh, scan, restart, getLogs, getMetrics, getTopology,
  };
}
