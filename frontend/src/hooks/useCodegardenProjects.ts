// frontend/src/hooks/useCodegardenProjects.ts
import { useState, useEffect, useCallback, useRef } from 'react';
import {
  CgProject,
  CgProjectListResponse,
  CgProjectCreateRequest,
  CgProjectUpdateRequest,
  GithubImportRequest,
  FromKnowledgeRequest,
  CandidateItem,
  CandidatesResponse,
  LifecycleStage,
  ProjectSourceType,
  ProjectType,
} from '../types/codegarden';

export interface UseCodegardenProjectsReturn {
  items: CgProject[];
  total: number;
  loading: boolean;
  error: string | null;

  // 过滤
  lifecycle: LifecycleStage | 'all';
  sourceType: ProjectSourceType | 'all';
  projectType: ProjectType | 'all';
  keyword: string;
  setLifecycle: (s: LifecycleStage | 'all') => void;
  setSourceType: (s: ProjectSourceType | 'all') => void;
  setProjectType: (t: ProjectType | 'all') => void;
  setKeyword: (k: string) => void;

  // CRUD
  refresh: () => Promise<void>;
  create: (req: CgProjectCreateRequest) => Promise<CgProject>;
  update: (id: string, req: CgProjectUpdateRequest) => Promise<CgProject>;
  remove: (id: string) => Promise<void>;
  archive: (id: string) => Promise<CgProject>;
  restore: (id: string) => Promise<CgProject>;
  transition: (id: string, to: LifecycleStage) => Promise<CgProject>;
  syncUpstream: (id: string) => Promise<{ task_id: number }>;
  importFromGithub: (req: GithubImportRequest) => Promise<CgProject>;
  importFromKnowledge: (req: FromKnowledgeRequest) => Promise<CgProject>;
  listCandidates: () => Promise<CandidateItem[]>;
}

export function useCodegardenProjects(): UseCodegardenProjectsReturn {
  const [items, setItems] = useState<CgProject[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [lifecycle, setLifecycle] = useState<LifecycleStage | 'all'>('all');
  const [sourceType, setSourceType] = useState<ProjectSourceType | 'all'>('all');
  const [projectType, setProjectType] = useState<ProjectType | 'all'>('all');
  const [keyword, setKeyword] = useState('');

  const abortRef = useRef<AbortController | null>(null);

  const fetchList = useCallback(async () => {
    if (abortRef.current) abortRef.current.abort();
    const ctrl = new AbortController();
    abortRef.current = ctrl;

    setLoading(true);
    setError(null);
    try {
      const params = new URLSearchParams({ limit: '200' });
      if (lifecycle !== 'all') params.set('lifecycle_stage', lifecycle);
      if (sourceType !== 'all') params.set('source_type', sourceType);
      if (projectType !== 'all') params.set('type', projectType);
      if (keyword.trim()) params.set('keyword', keyword.trim());

      const r = await fetch(`/api/codegarden/projects?${params}`, {
        signal: ctrl.signal,
        headers: { Accept: 'application/json' },
      });
      if (!r.ok) throw new Error(`请求失败 (${r.status})`);
      const data: CgProjectListResponse = await r.json();
      setItems(data.items || []);
      setTotal(data.total || 0);
    } catch (e: any) {
      if (e?.name === 'AbortError') return;
      setError(e?.message || '加载失败');
    } finally {
      if (abortRef.current === ctrl) setLoading(false);
    }
  }, [lifecycle, sourceType, projectType, keyword]);

  useEffect(() => {
    fetchList();
    return () => { if (abortRef.current) abortRef.current.abort(); };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    const t = setTimeout(() => fetchList(), 250);
    return () => clearTimeout(t);
  }, [fetchList]);

  const refresh = useCallback(async () => {
    await fetchList();
  }, [fetchList]);

  const create = useCallback(async (req: CgProjectCreateRequest): Promise<CgProject> => {
    const r = await fetch('/api/codegarden/projects', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
      body: JSON.stringify(req),
    });
    if (!r.ok) {
      const body = await r.text().catch(() => '');
      throw new Error(`新建失败 (${r.status})${body ? `: ${body}` : ''}`);
    }
    const item: CgProject = await r.json();
    setItems(prev => [item, ...prev]);
    setTotal(prev => prev + 1);
    return item;
  }, []);

  const update = useCallback(async (id: string, req: CgProjectUpdateRequest): Promise<CgProject> => {
    const r = await fetch(`/api/codegarden/projects/${id}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
      body: JSON.stringify(req),
    });
    if (!r.ok) {
      const body = await r.text().catch(() => '');
      throw new Error(`更新失败 (${r.status})${body ? `: ${body}` : ''}`);
    }
    const item: CgProject = await r.json();
    setItems(prev => prev.map(p => (p.id === id ? item : p)));
    return item;
  }, []);

  const remove = useCallback(async (id: string): Promise<void> => {
    const r = await fetch(`/api/codegarden/projects/${id}`, { method: 'DELETE' });
    if (!r.ok && r.status !== 204) throw new Error(`删除失败 (${r.status})`);
    setItems(prev => prev.filter(p => p.id !== id));
    setTotal(prev => Math.max(0, prev - 1));
  }, []);

  const archive = useCallback(async (id: string): Promise<CgProject> => {
    const r = await fetch(`/api/codegarden/projects/${id}/archive`, { method: 'POST' });
    if (!r.ok) throw new Error(`归档失败 (${r.status})`);
    const item: CgProject = await r.json();
    setItems(prev => prev.map(p => (p.id === id ? item : p)));
    return item;
  }, []);

  const restore = useCallback(async (id: string): Promise<CgProject> => {
    const r = await fetch(`/api/codegarden/projects/${id}/restore`, { method: 'POST' });
    if (!r.ok) throw new Error(`恢复失败 (${r.status})`);
    const item: CgProject = await r.json();
    setItems(prev => prev.map(p => (p.id === id ? item : p)));
    return item;
  }, []);

  const transition = useCallback(async (id: string, to: LifecycleStage): Promise<CgProject> => {
    const r = await fetch(`/api/codegarden/projects/${id}/lifecycle`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ to }),
    });
    if (!r.ok) {
      const body = await r.text().catch(() => '');
      throw new Error(`状态切换失败 (${r.status})${body ? `: ${body}` : ''}`);
    }
    const item: CgProject = await r.json();
    setItems(prev => prev.map(p => (p.id === id ? item : p)));
    return item;
  }, []);

  const syncUpstream = useCallback(async (id: string): Promise<{ task_id: number }> => {
    const r = await fetch(`/api/codegarden/projects/${id}/sync`, { method: 'POST' });
    if (r.status === 424) {
      throw new Error('未配置 github_token，请到 Secrets 页面添加');
    }
    if (!r.ok) throw new Error(`触发同步失败 (${r.status})`);
    const data = await r.json();
    return { task_id: data.task_id };
  }, []);

  const importFromGithub = useCallback(async (req: GithubImportRequest): Promise<CgProject> => {
    const r = await fetch('/api/codegarden/github/import', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(req),
    });
    if (r.status === 424) {
      throw new Error('未配置 github_token，请到 Secrets 页面添加');
    }
    if (!r.ok) {
      const body = await r.text().catch(() => '');
      throw new Error(`GitHub 导入失败 (${r.status})${body ? `: ${body}` : ''}`);
    }
    const item: CgProject = await r.json();
    setItems(prev => [item, ...prev]);
    setTotal(prev => prev + 1);
    return item;
  }, []);

  const importFromKnowledge = useCallback(async (req: FromKnowledgeRequest): Promise<CgProject> => {
    const r = await fetch('/api/codegarden/from-knowledge', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(req),
    });
    if (!r.ok) {
      const body = await r.text().catch(() => '');
      throw new Error(`从知识库导入失败 (${r.status})${body ? `: ${body}` : ''}`);
    }
    // 201 = 首次转化; 200 = 幂等 (已存在)
    const item: CgProject = await r.json();
    setItems(prev => {
      const exists = prev.some(p => p.id === item.id);
      return exists ? prev.map(p => (p.id === item.id ? item : p)) : [item, ...prev];
    });
    setTotal(prev => prev);  // 幂等时不增加 total
    return item;
  }, []);

  const listCandidates = useCallback(async (): Promise<CandidateItem[]> => {
    const r = await fetch('/api/codegarden/candidates');
    if (!r.ok) throw new Error(`候选列表加载失败 (${r.status})`);
    const data: CandidatesResponse = await r.json();
    return data.items || [];
  }, []);

  return {
    items, total, loading, error,
    lifecycle, sourceType, projectType, keyword,
    setLifecycle, setSourceType, setProjectType, setKeyword,
    refresh, create, update, remove,
    archive, restore, transition, syncUpstream,
    importFromGithub, importFromKnowledge, listCandidates,
  };
}
