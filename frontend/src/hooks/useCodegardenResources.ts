// frontend/src/hooks/useCodegardenResources.ts
import { useState, useEffect, useCallback, useRef } from 'react';
import {
  CgResource,
  ResourceType,
  ResourceStatus,
  AllocatePortRequest,
  SaveEnvTemplateRequest,
} from '../types/codegarden';
import {
  listResources,
  allocatePort as apiAllocatePort,
  releasePort as apiReleasePort,
  saveEnvTemplate as apiSaveEnvTemplate,
  loadEnvTemplate,
  deleteResource,
} from '../api/codegarden';

export interface UseCodegardenResourcesReturn {
  items: CgResource[];
  total: number;
  loading: boolean;
  error: string | null;
  resourceType: ResourceType | 'all';
  resourceStatus: ResourceStatus | 'all';
  setResourceType: (v: ResourceType | 'all') => void;
  setResourceStatus: (v: ResourceStatus | 'all') => void;
  refresh: () => Promise<void>;
  allocatePort: (req: AllocatePortRequest) => Promise<CgResource>;
  releasePort: (port: number) => Promise<void>;
  saveEnvTemplate: (req: SaveEnvTemplateRequest) => Promise<void>;
  loadEnvTemplate: (name: string) => Promise<Record<string, unknown>>;
  remove: (id: string) => Promise<void>;
}

export function useCodegardenResources(): UseCodegardenResourcesReturn {
  const [items, setItems] = useState<CgResource[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [resourceType, setResourceType] = useState<ResourceType | 'all'>('all');
  const [resourceStatus, setResourceStatus] = useState<ResourceStatus | 'all'>('all');

  const abortRef = useRef<AbortController | null>(null);

  const fetchList = useCallback(async () => {
    if (abortRef.current) abortRef.current.abort();
    const ctrl = new AbortController();
    abortRef.current = ctrl;
    setLoading(true);
    setError(null);
    try {
      const data = await listResources(
        {
          limit: 500,
          type: resourceType !== 'all' ? resourceType : undefined,
          status: resourceStatus !== 'all' ? resourceStatus : undefined,
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
  }, [resourceType, resourceStatus]);

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

  const allocatePort = useCallback(async (req: AllocatePortRequest): Promise<CgResource> => {
    const item: CgResource = await apiAllocatePort(req);
    await fetchList();
    return item;
  }, [fetchList]);

  const releasePort = useCallback(async (port: number): Promise<void> => {
    await apiReleasePort(port);
    await fetchList();
  }, [fetchList]);

  const saveEnvTemplate = useCallback(async (req: SaveEnvTemplateRequest): Promise<void> => {
    await apiSaveEnvTemplate(req);
  }, []);

  const loadEnvTemplateByName = useCallback(async (name: string): Promise<Record<string, unknown>> => {
    const data = await loadEnvTemplate(name);
    return data.env_vars || {};
  }, []);

  const remove = useCallback(async (id: string): Promise<void> => {
    await deleteResource(id);
    setItems(prev => prev.filter(p => p.id !== id));
    setTotal(prev => Math.max(0, prev - 1));
  }, []);

  return {
    items, total, loading, error,
    resourceType, resourceStatus,
    setResourceType, setResourceStatus,
    refresh, allocatePort, releasePort,
    saveEnvTemplate, loadEnvTemplate: loadEnvTemplateByName, remove,
  };
}
