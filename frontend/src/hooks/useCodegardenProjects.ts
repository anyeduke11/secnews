// frontend/src/hooks/useCodegardenProjects.ts
import { useState, useEffect, useCallback, useRef } from 'react';
import {
  CgProject,
  CgProjectCreateRequest,
  CgProjectUpdateRequest,
  GithubImportRequest,
  FromKnowledgeRequest,
  CandidateItem,
  LifecycleStage,
  ProjectSourceType,
  ProjectType,
} from '../types/codegarden';
import {
  listProjects,
  createProject,
  updateProject,
  deleteProject,
  archiveProject,
  restoreProject,
  transitionProject,
  syncProjectUpstream,
  importFromGithub as apiImportFromGithub,
  importFromKnowledge as apiImportFromKnowledge,
  listCandidates as apiListCandidates,
} from '../api/codegarden';

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
      const data = await listProjects(
        {
          limit: 200,
          lifecycle_stage: lifecycle !== 'all' ? lifecycle : undefined,
          source_type: sourceType !== 'all' ? sourceType : undefined,
          type: projectType !== 'all' ? projectType : undefined,
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
    const item: CgProject = await createProject(req);
    setItems(prev => [item, ...prev]);
    setTotal(prev => prev + 1);
    return item;
  }, []);

  const update = useCallback(async (id: string, req: CgProjectUpdateRequest): Promise<CgProject> => {
    const item: CgProject = await updateProject(id, req);
    setItems(prev => prev.map(p => (p.id === id ? item : p)));
    return item;
  }, []);

  const remove = useCallback(async (id: string): Promise<void> => {
    await deleteProject(id);
    setItems(prev => prev.filter(p => p.id !== id));
    setTotal(prev => Math.max(0, prev - 1));
  }, []);

  const archive = useCallback(async (id: string): Promise<CgProject> => {
    const item: CgProject = await archiveProject(id);
    setItems(prev => prev.map(p => (p.id === id ? item : p)));
    return item;
  }, []);

  const restore = useCallback(async (id: string): Promise<CgProject> => {
    const item: CgProject = await restoreProject(id);
    setItems(prev => prev.map(p => (p.id === id ? item : p)));
    return item;
  }, []);

  const transition = useCallback(async (id: string, to: LifecycleStage): Promise<CgProject> => {
    const item: CgProject = await transitionProject(id, to);
    setItems(prev => prev.map(p => (p.id === id ? item : p)));
    return item;
  }, []);

  const syncUpstream = useCallback(async (id: string): Promise<{ task_id: number }> => {
    const data = await syncProjectUpstream(id);
    return { task_id: data.task_id };
  }, []);

  const importFromGithub = useCallback(async (req: GithubImportRequest): Promise<CgProject> => {
    const item: CgProject = await apiImportFromGithub(req);
    setItems(prev => [item, ...prev]);
    setTotal(prev => prev + 1);
    return item;
  }, []);

  const importFromKnowledge = useCallback(async (req: FromKnowledgeRequest): Promise<CgProject> => {
    // 201 = 首次转化; 200 = 幂等 (已存在)
    const item: CgProject = await apiImportFromKnowledge(req);
    setItems(prev => {
      const exists = prev.some(p => p.id === item.id);
      return exists ? prev.map(p => (p.id === item.id ? item : p)) : [item, ...prev];
    });
    setTotal(prev => prev);  // 幂等时不增加 total
    return item;
  }, []);

  const listCandidates = useCallback(async (): Promise<CandidateItem[]> => {
    const data = await apiListCandidates();
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
