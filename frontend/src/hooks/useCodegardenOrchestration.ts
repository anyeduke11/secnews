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
import {
  listDependencies,
  addDependency as apiAddDependency,
  removeDependency as apiRemoveDependency,
  analyzeDependencyImpact,
  listEvents,
  publishEvent as apiPublishEvent,
  listPlaybooks,
  runPlaybook as apiRunPlaybook,
} from '../api/codegarden';

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
      const data = await listDependencies(500);
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
      const data = await listEvents(
        {
          limit: 200,
          event_type: eventType !== 'all' ? eventType : undefined,
          status: eventStatus !== 'all' ? eventStatus : undefined,
        },
        { signal: ctrl.signal },
      );
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
      const data = await listPlaybooks();
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
    const item: CgDependency = await apiAddDependency(req);
    setDependencies(prev => [item, ...prev]);
    return item;
  }, []);

  const removeDependency = useCallback(async (id: string): Promise<void> => {
    await apiRemoveDependency(id);
    setDependencies(prev => prev.filter(d => d.id !== id));
  }, []);

  const impactAnalysis = useCallback(async (
    targetType: DepEntityType,
    targetId: string,
    maxDepth = 5,
  ): Promise<CgDependency[]> => {
    const data = await analyzeDependencyImpact(targetType, targetId, maxDepth);
    return data.impacts || [];
  }, []);

  const publishEvent = useCallback(async (req: {
    event_type: EventType;
    source_type: 'project' | 'service' | 'resource' | 'scheduler';
    source_id: string;
    payload?: Record<string, unknown>;
  }): Promise<CgEvent> => {
    const item: CgEvent = await apiPublishEvent(req);
    setEvents(prev => [item, ...prev]);
    return item;
  }, []);

  const runPlaybook = useCallback(async (name: string, params?: Record<string, unknown>): Promise<RunPlaybookResponse> => {
    return await apiRunPlaybook(name, params);
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
