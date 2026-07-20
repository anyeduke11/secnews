// frontend/src/hooks/useCodegardenResources.ts
import { useState, useEffect, useCallback, useRef } from 'react';
import {
  CgResource,
  CgResourceListResponse,
  ResourceType,
  ResourceStatus,
  AllocatePortRequest,
  SaveEnvTemplateRequest,
} from '../types/codegarden';

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
      const params = new URLSearchParams({ limit: '500' });
      if (resourceType !== 'all') params.set('type', resourceType);
      if (resourceStatus !== 'all') params.set('status', resourceStatus);

      const r = await fetch(`/api/codegarden/resources?${params}`, {
        signal: ctrl.signal,
        headers: { Accept: 'application/json' },
      });
      if (!r.ok) throw new Error(`请求失败 (${r.status})`);
      const data: CgResourceListResponse = await r.json();
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
    const r = await fetch('/api/codegarden/resources/allocate-port', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(req),
    });
    if (!r.ok) {
      const body = await r.text().catch(() => '');
      throw new Error(`端口分配失败 (${r.status})${body ? `: ${body}` : ''}`);
    }
    const item: CgResource = await r.json();
    await fetchList();
    return item;
  }, [fetchList]);

  const releasePort = useCallback(async (port: number): Promise<void> => {
    const r = await fetch(`/api/codegarden/resources/release-port?port=${port}`, { method: 'POST' });
    if (!r.ok) {
      const body = await r.text().catch(() => '');
      throw new Error(`端口释放失败 (${r.status})${body ? `: ${body}` : ''}`);
    }
    await fetchList();
  }, [fetchList]);

  const saveEnvTemplate = useCallback(async (req: SaveEnvTemplateRequest): Promise<void> => {
    const r = await fetch('/api/codegarden/resources/env-templates', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(req),
    });
    if (!r.ok) throw new Error(`环境模板保存失败 (${r.status})`);
  }, []);

  const loadEnvTemplate = useCallback(async (name: string): Promise<Record<string, unknown>> => {
    const r = await fetch(`/api/codegarden/resources/env-templates?name=${encodeURIComponent(name)}`);
    if (!r.ok) throw new Error(`环境模板加载失败 (${r.status})`);
    const data = await r.json();
    return data.env_vars || {};
  }, []);

  const remove = useCallback(async (id: string): Promise<void> => {
    const r = await fetch(`/api/codegarden/resources/${id}`, { method: 'DELETE' });
    if (!r.ok && r.status !== 204) throw new Error(`删除失败 (${r.status})`);
    setItems(prev => prev.filter(p => p.id !== id));
    setTotal(prev => Math.max(0, prev - 1));
  }, []);

  return {
    items, total, loading, error,
    resourceType, resourceStatus,
    setResourceType, setResourceStatus,
    refresh, allocatePort, releasePort,
    saveEnvTemplate, loadEnvTemplate, remove,
  };
}
