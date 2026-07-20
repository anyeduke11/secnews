// frontend/src/hooks/useCodegardenOrchestration.ts
import { useState, useEffect, useCallback, useRef } from 'react';
import {
  CgDependency,
  CgEvent,
  Playbook,
  RunPlaybookResponse,
  EventType,
  EventStatus,
  DepEntityType,
  DepType,
} from '../types/codegarden';

export interface UseCodegardenOrchestrationReturn {
  dependencies: CgDependency[];
  events: CgEvent[];
  playbooks: Playbook[];
  loadingDeps: boolean;
  loadingEvents: boolean;
  loadingPlaybooks: boolean;
  error: string | null;
  eventType: EventType | 'all';
  eventStatus: EventStatus | 'all';
  setEventType: (v: EventType | 'all') => void;
  setEventStatus: (v: EventStatus | 'all') => void;
  refreshDeps: () => Promise<void>;
  refreshEvents: () => Promise<void>;
  refreshPlaybooks: () => Promise<void>;
  addDependency: (req: {
    source_type: DepEntityType;
    source_id: string;
    target_type: DepEntityType;
    target_id: string;
    dep_type: DepType;
    metadata?: Record<string, unknown>;
  }) => Promise<CgDependency>;
  removeDependency: (id: string) => Promise<void>;
  impactAnalysis: (targetType: DepEntityType, targetId: string, maxDepth?: number) => Promise<CgDependency[]>;
  publishEvent: (req: {
    event_type: EventType;
    source_type: 'project' | 'service' | 'resource' | 'scheduler';
    source_id: string;
    payload?: Record<string, unknown>;
  }) => Promise<CgEvent>;
  runPlaybook: (name: string, params?: Record<string, unknown>) => Promise<RunPlaybookResponse>;
}

export function useCodegardenOrchestration(): UseCodegardenOrchestrationReturn {
  const [dependencies, setDependencies] = useState<CgDependency[]>([]);
  const [events, setEvents] = useState<CgEvent[]>([]);
  const [playbooks, setPlaybooks] = useState<Playbook[]>([]);
  const [loadingDeps, setLoadingDeps] = useState(false);
  const [loadingEvents, setLoadingEvents] = useState(false);
  const [loadingPlaybooks, setLoadingPlaybooks] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [eventType, setEventType] = useState<EventType | 'all'>('all');
  const [eventStatus, setEventStatus] = useState<EventStatus | 'all'>('all');

  const abortRef = useRef<AbortController | null>(null);

  const refreshDeps = useCallback(async () => {
    setLoadingDeps(true);
    try {
      const r = await fetch('/api/codegarden/dependencies?limit=500');
      if (!r.ok) throw new Error(`请求失败 (${r.status})`);
      const data = await r.json();
      setDependencies(data.items || []);
    } catch (e: any) {
      setError(e?.message || '加载依赖失败');
    } finally {
      setLoadingDeps(false);
    }
  }, []);

  const refreshEvents = useCallback(async () => {
    if (abortRef.current) abortRef.current.abort();
    const ctrl = new AbortController();
    abortRef.current = ctrl;
    setLoadingEvents(true);
    try {
      const params = new URLSearchParams({ limit: '200' });
      if (eventType !== 'all') params.set('event_type', eventType);
      if (eventStatus !== 'all') params.set('status', eventStatus);
      const r = await fetch(`/api/codegarden/events?${params}`, { signal: ctrl.signal });
      if (!r.ok) throw new Error(`请求失败 (${r.status})`);
      const data = await r.json();
      setEvents(data.items || []);
    } catch (e: any) {
      if (e?.name === 'AbortError') return;
      setError(e?.message || '加载事件失败');
    } finally {
      if (abortRef.current === ctrl) setLoadingEvents(false);
    }
  }, [eventType, eventStatus]);

  const refreshPlaybooks = useCallback(async () => {
    setLoadingPlaybooks(true);
    try {
      const r = await fetch('/api/codegarden/playbooks');
      if (!r.ok) throw new Error(`请求失败 (${r.status})`);
      const data = await r.json();
      setPlaybooks(data.items || []);
    } catch (e: any) {
      setError(e?.message || '加载 Playbook 失败');
    } finally {
      setLoadingPlaybooks(false);
    }
  }, []);

  useEffect(() => {
    refreshDeps();
    refreshEvents();
    refreshPlaybooks();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    const t = setTimeout(() => refreshEvents(), 250);
    return () => clearTimeout(t);
  }, [refreshEvents]);

  const addDependency = useCallback(async (req: {
    source_type: DepEntityType;
    source_id: string;
    target_type: DepEntityType;
    target_id: string;
    dep_type: DepType;
    metadata?: Record<string, unknown>;
  }): Promise<CgDependency> => {
    const r = await fetch('/api/codegarden/dependencies', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(req),
    });
    if (!r.ok) {
      const body = await r.text().catch(() => '');
      throw new Error(`添加依赖失败 (${r.status})${body ? `: ${body}` : ''}`);
    }
    const item: CgDependency = await r.json();
    setDependencies(prev => [item, ...prev]);
    return item;
  }, []);

  const removeDependency = useCallback(async (id: string): Promise<void> => {
    const r = await fetch(`/api/codegarden/dependencies/${id}`, { method: 'DELETE' });
    if (!r.ok && r.status !== 204) throw new Error(`删除依赖失败 (${r.status})`);
    setDependencies(prev => prev.filter(d => d.id !== id));
  }, []);

  const impactAnalysis = useCallback(async (
    targetType: DepEntityType,
    targetId: string,
    maxDepth = 5,
  ): Promise<CgDependency[]> => {
    const r = await fetch(
      `/api/codegarden/dependencies/impact?target_type=${targetType}&target_id=${targetId}&max_depth=${maxDepth}`,
    );
    if (!r.ok) throw new Error(`影响分析失败 (${r.status})`);
    const data = await r.json();
    return data.items || [];
  }, []);

  const publishEvent = useCallback(async (req: {
    event_type: EventType;
    source_type: 'project' | 'service' | 'resource' | 'scheduler';
    source_id: string;
    payload?: Record<string, unknown>;
  }): Promise<CgEvent> => {
    const r = await fetch('/api/codegarden/events', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(req),
    });
    if (!r.ok) throw new Error(`事件发布失败 (${r.status})`);
    const item: CgEvent = await r.json();
    setEvents(prev => [item, ...prev]);
    return item;
  }, []);

  const runPlaybook = useCallback(async (name: string, params?: Record<string, unknown>): Promise<RunPlaybookResponse> => {
    const r = await fetch(`/api/codegarden/playbooks/${encodeURIComponent(name)}/run`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ params: params || {} }),
    });
    if (!r.ok) throw new Error(`Playbook 执行失败 (${r.status})`);
    return await r.json();
  }, []);

  return {
    dependencies, events, playbooks,
    loadingDeps, loadingEvents, loadingPlaybooks,
    error,
    eventType, eventStatus, setEventType, setEventStatus,
    refreshDeps, refreshEvents, refreshPlaybooks,
    addDependency, removeDependency, impactAnalysis,
    publishEvent, runPlaybook,
  };
}
