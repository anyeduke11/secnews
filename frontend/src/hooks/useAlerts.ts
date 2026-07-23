import { useState, useEffect, useCallback, useRef } from 'react';
import { useSSE } from './useSSE';

/**
 * v1.7 Phase 3 — 告警 Hook (含 SSE 实时推送)
 *
 * 对接后端:
 *  - GET    /api/alerts                    告警列表 (支持 status 过滤)
 *  - PUT    /api/alerts/{id}/read          标记已读
 *  - PUT    /api/alerts/{id}/dismiss       忽略
 *  - DELETE /api/alerts/{id}               删除
 *  - POST   /api/alerts/evaluate/{hotspot_id}  手动评估
 *  - SSE    /api/events                    实时推送 event_type="alert"
 *
 * 验收 3: 告警 SSE 推送到达前端 — useSSE 监听 "alert" 事件并追加到列表头部。
 */

export interface Alert {
  id: string;
  rule_id: string;
  entity_type: string;
  entity_id: string;
  payload: any;
  status: string;
  created_at: string;
  processed_at: string | null;
}

export interface AlertRule {
  id: string;
  name: string;
  condition: any;
  action: any;
  cooldown_sec: number;
  enabled: boolean;
  last_fired_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface UseAlertsReturn {
  alerts: Alert[];
  unreadCount: number;
  loading: boolean;
  error: string | null;
  connected: boolean;
  markRead: (id: string) => Promise<void>;
  dismiss: (id: string) => Promise<void>;
  remove: (id: string) => Promise<void>;
  evaluate: (hotspotId: string) => Promise<string[]>;
  refresh: () => Promise<void>;
}

export function useAlerts(status?: string): UseAlertsReturn {
  const [alerts, setAlerts] = useState<Alert[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const statusRef = useRef(status);
  statusRef.current = status;

  const refresh = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const params = new URLSearchParams();
      if (statusRef.current) params.set('status', statusRef.current);
      const r = await fetch(`/api/alerts?${params}`, {
        headers: { Accept: 'application/json' },
      });
      if (!r.ok) throw new Error(`请求失败 (${r.status})`);
      const data = await r.json();
      setAlerts(data.items || []);
    } catch (e: any) {
      setError(e?.message || '告警加载失败');
    } finally {
      setLoading(false);
    }
  }, []);

  // 初始加载
  useEffect(() => {
    refresh();
  }, [refresh]);

  // SSE: 监听 "alert" 事件, 追加新告警到列表头部
  const { connected } = useSSE({
    onEvent: useCallback((type: string, data: any) => {
      if (type === 'alert' && data?.alert) {
        setAlerts((prev) => {
          // 去重: 避免同一告警重复添加
          const exists = prev.some((a) => a.id === data.alert.id);
          if (exists) return prev;
          return [data.alert, ...prev];
        });
      }
    }, []),
  });

  const markRead = useCallback(async (id: string) => {
    const r = await fetch(`/api/alerts/${encodeURIComponent(id)}/read`, {
      method: 'PUT',
      headers: { Accept: 'application/json' },
    });
    if (!r.ok) throw new Error(`标记已读失败 (${r.status})`);
    setAlerts((prev) =>
      prev.map((a) => (a.id === id ? { ...a, status: 'read' } : a))
    );
  }, []);

  const dismiss = useCallback(async (id: string) => {
    const r = await fetch(`/api/alerts/${encodeURIComponent(id)}/dismiss`, {
      method: 'PUT',
      headers: { Accept: 'application/json' },
    });
    if (!r.ok) throw new Error(`忽略告警失败 (${r.status})`);
    setAlerts((prev) =>
      prev.map((a) => (a.id === id ? { ...a, status: 'dismissed' } : a))
    );
  }, []);

  const remove = useCallback(async (id: string) => {
    const r = await fetch(`/api/alerts/${encodeURIComponent(id)}`, {
      method: 'DELETE',
      headers: { Accept: 'application/json' },
    });
    if (!r.ok) throw new Error(`删除告警失败 (${r.status})`);
    setAlerts((prev) => prev.filter((a) => a.id !== id));
  }, []);

  const evaluate = useCallback(async (hotspotId: string): Promise<string[]> => {
    const r = await fetch(
      `/api/alerts/evaluate/${encodeURIComponent(hotspotId)}`,
      { method: 'POST', headers: { Accept: 'application/json' } }
    );
    if (!r.ok) throw new Error(`评估失败 (${r.status})`);
    const data = await r.json();
    // 评估后刷新列表 (可能产生新告警)
    refresh();
    return data.fired || [];
  }, [refresh]);

  const unreadCount = alerts.filter(
    (a) => a.status === 'pending' || a.status === 'fired'
  ).length;

  return {
    alerts,
    unreadCount,
    loading,
    error,
    connected,
    markRead,
    dismiss,
    remove,
    evaluate,
    refresh,
  };
}
