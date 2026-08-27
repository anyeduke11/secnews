// AlertCenter — Phase 12 告警中心
// 告警事件列表、未读计数、标记已读/解决、手动评估触发
import { useEffect, useState, useCallback } from 'react';

interface AlertEvent {
  id: number;
  rule_type: string;
  title: string;
  description: string;
  severity: 'critical' | 'high' | 'medium' | 'low';
  source: string;
  source_url: string | null;
  status: 'unread' | 'read' | 'resolved';
  created_at: string;
}

interface AlertListResponse {
  count: number;
  items: AlertEvent[];
}

const SEVERITY_COLORS: Record<string, string> = {
  critical: '#dc2626',
  high: '#ea580c',
  medium: '#ca8a04',
  low: '#6b7280',
};

const SEVERITY_LABELS: Record<string, string> = {
  critical: '严重',
  high: '高',
  medium: '中',
  low: '低',
};

const STATUS_LABELS: Record<string, string> = {
  unread: '未读',
  read: '已读',
  resolved: '已解决',
};

const API_BASE = '/api/alerts/v2';

async function fetchAlerts(status?: string): Promise<AlertEvent[]> {
  const params = new URLSearchParams();
  if (status) params.set('status', status);
  params.set('limit', '50');
  const res = await fetch(`${API_BASE}?${params}`);
  const data: AlertListResponse = await res.json();
  return data.items || [];
}

async function fetchUnreadCount(): Promise<number> {
  const res = await fetch(`${API_BASE}/unread-count`);
  const data = await res.json();
  return data.count || 0;
}

async function markRead(id: number): Promise<void> {
  await fetch(`${API_BASE}/${id}/read`, { method: 'PUT' });
}

async function markAllRead(): Promise<void> {
  await fetch(`${API_BASE}/read-all`, { method: 'PUT' });
}

async function resolveAlert(id: number): Promise<void> {
  await fetch(`${API_BASE}/${id}/resolve`, { method: 'PUT' });
}

async function evaluateRules(): Promise<void> {
  await fetch(`${API_BASE}/evaluate`, { method: 'POST' });
}

function formatAlertTime(isoString: string): string {
  const d = new Date(isoString);
  const month = d.getMonth() + 1;
  const day = d.getDate();
  const hour = d.getHours().toString().padStart(2, '0');
  const min = d.getMinutes().toString().padStart(2, '0');
  return `${month}/${day} ${hour}:${min}`;
}

export default function AlertCenter() {
  const [alerts, setAlerts] = useState<AlertEvent[]>([]);
  const [unreadCount, setUnreadCount] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [evaluating, setEvaluating] = useState(false);
  const [statusFilter, setStatusFilter] = useState<string | undefined>(undefined);

  const loadAlerts = useCallback(async () => {
    try {
      setError(null);
      const items = await fetchAlerts(statusFilter);
      setAlerts(items);
    } catch (e: any) {
      setError(e.message || '加载告警失败');
    } finally {
      setLoading(false);
    }
  }, [statusFilter]);

  const loadUnreadCount = useCallback(async () => {
    try {
      const count = await fetchUnreadCount();
      setUnreadCount(count);
    } catch {
      // 静默失败，不影响主列表
    }
  }, []);

  // 初始加载
  useEffect(() => {
    loadAlerts();
    loadUnreadCount();
  }, [loadAlerts, loadUnreadCount]);

  // 每 30 秒轮询未读计数
  useEffect(() => {
    const t = window.setInterval(loadUnreadCount, 30000);
    return () => window.clearInterval(t);
  }, [loadUnreadCount]);

  const handleMarkRead = useCallback(async (id: number) => {
    try {
      await markRead(id);
      setAlerts(prev => prev.map(a => (a.id === id ? { ...a, status: 'read' as const } : a)));
      setUnreadCount(prev => Math.max(0, prev - 1));
    } catch {
      // 静默失败
    }
  }, []);

  const handleMarkAllRead = useCallback(async () => {
    try {
      await markAllRead();
      setAlerts(prev => prev.map(a => (a.status === 'unread' ? { ...a, status: 'read' as const } : a)));
      setUnreadCount(0);
    } catch {
      // 静默失败
    }
  }, []);

  const handleResolve = useCallback(async (id: number) => {
    try {
      await resolveAlert(id);
      setAlerts(prev => prev.map(a => (a.id === id ? { ...a, status: 'resolved' as const } : a)));
      if (alerts.find(a => a.id === id)?.status === 'unread') {
        setUnreadCount(prev => Math.max(0, prev - 1));
      }
    } catch {
      // 静默失败
    }
  }, [alerts]);

  const handleEvaluate = useCallback(async () => {
    setEvaluating(true);
    try {
      await evaluateRules();
      // 评估完成后刷新列表
      await loadAlerts();
      await loadUnreadCount();
    } catch {
      // 静默失败
    } finally {
      setEvaluating(false);
    }
  }, [loadAlerts, loadUnreadCount]);

  return (
    <div className="space-y-4">
      {/* 顶栏：未读计数横幅 + 操作按钮 */}
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-3">
          <h2 className="font-mono text-lg font-bold" style={{ color: 'var(--text-primary)' }}>
            告警中心
          </h2>
          {unreadCount > 0 && (
            <span
              className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-sm text-xs font-bold"
              style={{
                backgroundColor: 'color-mix(in srgb, #dc2626 12%, transparent)',
                color: '#dc2626',
                border: '1px solid color-mix(in srgb, #dc2626 25%, transparent)',
              }}
            >
              <span className="w-1.5 h-1.5 rounded-full inline-block" style={{ backgroundColor: '#dc2626' }} />
              {unreadCount} 条未读告警
            </span>
          )}
        </div>
        <div className="flex items-center gap-2">
          <button
            type="button"
            className="btn-ghost"
            onClick={handleEvaluate}
            disabled={evaluating}
          >
            {evaluating ? '评估中…' : '评估规则'}
          </button>
          {unreadCount > 0 && (
            <button
              type="button"
              className="btn-accent"
              onClick={handleMarkAllRead}
            >
              全部已读
            </button>
          )}
        </div>
      </div>

      {/* 筛选栏 */}
      <div className="flex items-center gap-2">
        <span className="text-xs" style={{ color: 'var(--text-muted)' }}>筛选:</span>
        {[
          { value: undefined, label: '全部' },
          { value: 'unread', label: '未读' },
          { value: 'read', label: '已读' },
          { value: 'resolved', label: '已解决' },
        ].map(opt => (
          <button
            key={opt.label}
            type="button"
            className={`ink-chip ${statusFilter === opt.value ? 'active' : ''}`}
            onClick={() => setStatusFilter(opt.value)}
            style={{ fontSize: '11.5px' }}
          >
            {opt.label}
          </button>
        ))}
      </div>

      {/* 错误提示 */}
      {error && (
        <div
          className="text-xs px-3 py-2 rounded-sm"
          style={{
            color: 'var(--color-error)',
            backgroundColor: 'color-mix(in srgb, var(--color-error) 10%, transparent)',
            border: '1px solid color-mix(in srgb, var(--color-error) 20%, transparent)',
          }}
        >
          {error}
          <button
            type="button"
            className="ml-2 underline"
            style={{ color: 'var(--color-error)' }}
            onClick={loadAlerts}
          >
            重试
          </button>
        </div>
      )}

      {/* 加载态 */}
      {loading && (
        <div className="space-y-2">
          {[1, 2, 3].map(i => (
            <div
              key={i}
              className="animate-shimmer rounded-sm"
              style={{ height: 64, backgroundColor: 'var(--bg-hover)' }}
            />
          ))}
        </div>
      )}

      {/* 空态 */}
      {!loading && !error && alerts.length === 0 && (
        <div className="text-center py-12">
          <p className="text-sm" style={{ color: 'var(--text-muted)' }}>
            暂无告警
          </p>
        </div>
      )}

      {/* 告警列表 */}
      {!loading && alerts.length > 0 && (
        <div className="space-y-2">
          {alerts.map(alert => {
            const severityColor = SEVERITY_COLORS[alert.severity] || '#6b7280';
            return (
              <div
                key={alert.id}
                className="card-base"
                style={{
                  padding: '12px 14px',
                  borderLeft: `3px solid ${severityColor}`,
                  opacity: alert.status === 'resolved' ? 0.6 : 1,
                }}
              >
                <div className="flex items-start justify-between gap-3">
                  {/* 左侧：严重度 + 内容 */}
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 mb-1">
                      {/* 严重度指示器 */}
                      <span
                        className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded-sm text-[10px] font-bold uppercase"
                        style={{
                          color: severityColor,
                          border: `1px solid color-mix(in srgb, ${severityColor} 35%, transparent)`,
                        }}
                      >
                        <span
                          className="w-1.5 h-1.5 rounded-full inline-block"
                          style={{ backgroundColor: severityColor }}
                        />
                        {SEVERITY_LABELS[alert.severity] || alert.severity}
                      </span>
                      {/* 状态徽章 */}
                      <span
                        className="text-[10px] font-mono px-1.5 py-0.5 rounded-sm"
                        style={{
                          color: 'var(--text-muted)',
                          border: '1px solid var(--border-color)',
                        }}
                      >
                        {STATUS_LABELS[alert.status] || alert.status}
                      </span>
                      {/* 来源 */}
                      <span
                        className="text-[10px] font-mono truncate"
                        style={{ color: 'var(--text-muted)' }}
                        title={alert.source}
                      >
                        {alert.source}
                      </span>
                    </div>
                    <h3
                      className="font-mono font-bold text-sm leading-snug mb-0.5"
                      style={{ color: 'var(--text-primary)' }}
                    >
                      {alert.title}
                    </h3>
                    <p
                      className="text-xs leading-relaxed line-clamp-2"
                      style={{ color: 'var(--text-secondary)' }}
                      title={alert.description}
                    >
                      {alert.description}
                    </p>
                    <div className="flex items-center gap-2 mt-1.5">
                      <span className="text-[10px] font-mono" style={{ color: 'var(--text-muted)' }}>
                        {formatAlertTime(alert.created_at)}
                      </span>
                      <span className="text-[10px] font-mono" style={{ color: 'var(--text-muted)' }}>
                        {alert.rule_type}
                      </span>
                    </div>
                  </div>
                  {/* 右侧：操作按钮 */}
                  <div className="flex items-center gap-1 flex-shrink-0">
                    {alert.status === 'unread' && (
                      <button
                        type="button"
                        className="btn-ghost"
                        style={{ fontSize: '10.5px', padding: '2px 8px', minHeight: 24 }}
                        onClick={() => handleMarkRead(alert.id)}
                        title="标记已读"
                      >
                        已读
                      </button>
                    )}
                    {alert.status !== 'resolved' && (
                      <button
                        type="button"
                        className="btn-ghost"
                        style={{ fontSize: '10.5px', padding: '2px 8px', minHeight: 24 }}
                        onClick={() => handleResolve(alert.id)}
                        title="标记已解决"
                      >
                        解决
                      </button>
                    )}
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
