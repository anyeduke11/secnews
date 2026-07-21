// frontend/src/components/codegarden/EventBus.tsx
// M4 事件总线 — 事件实时列表 + 按 type/status 筛选 + 手动发布
// Phase 4: 错误/成功 toast 走 --color-error/--color-success, 状态色映射到 token
import { useState } from 'react';
import {
  CgEvent,
  EventType,
  EventStatus,
  EventSourceType,
  EVENT_TYPE_LABELS,
} from '../../types/codegarden';
import { useCodegardenOrchestration } from '../../hooks/useCodegardenOrchestration';
import { Icon } from '../Icon';
import { useThemeColors, ThemeColorKey } from '../../hooks/useThemeColors';
import { EmptyState } from '../EmptyState';

const EVENT_TYPE_OPTIONS: Array<EventType | 'all'> = [
  'all', 'code_push', 'service_error', 'port_conflict', 'dep_update', 'project_archive',
];

const STATUS_OPTIONS: Array<EventStatus | 'all'> = ['all', 'pending', 'processed', 'failed'];

const SOURCE_LABELS: Record<EventSourceType, string> = {
  project: '项目', service: '服务', resource: '资源', scheduler: '调度器',
};

// 事件状态 → token key (border-left 需要字面色)
const STATUS_TOKEN: Record<EventStatus, ThemeColorKey> = {
  pending: 'color-warning',
  processed: 'color-success',
  failed: 'color-error',
};

export function EventBus() {
  const {
    events, loadingEvents, error,
    eventType, eventStatus, setEventType, setEventStatus,
    refreshEvents, publishEvent,
  } = useCodegardenOrchestration();
  const [showPublish, setShowPublish] = useState(false);
  const [toast, setToast] = useState<{ kind: 'ok' | 'err'; msg: string } | null>(null);

  const colors = useThemeColors(['color-warning', 'color-success', 'color-error']);

  const flash = (kind: 'ok' | 'err', msg: string) => {
    setToast({ kind, msg });
    setTimeout(() => setToast(null), 3000);
  };

  return (
    <div>
      <div className="flex items-center justify-between mb-3 flex-wrap gap-2">
        <div className="flex items-center gap-2 flex-wrap">
          <select
            value={eventType}
            onChange={(e) => setEventType(e.target.value as EventType | 'all')}
            className="text-[11px] px-2 py-1 rounded"
            style={{ backgroundColor: 'var(--bg-hover)', color: 'var(--text-primary)', border: '1px solid var(--border-color)' }}
          >
            {EVENT_TYPE_OPTIONS.map(t => (
              <option key={t} value={t}>{t === 'all' ? '全部类型' : EVENT_TYPE_LABELS[t as EventType]}</option>
            ))}
          </select>
          <select
            value={eventStatus}
            onChange={(e) => setEventStatus(e.target.value as EventStatus | 'all')}
            className="text-[11px] px-2 py-1 rounded"
            style={{ backgroundColor: 'var(--bg-hover)', color: 'var(--text-primary)', border: '1px solid var(--border-color)' }}
          >
            {STATUS_OPTIONS.map(s => <option key={s} value={s}>{s === 'all' ? '全部状态' : s}</option>)}
          </select>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={() => setShowPublish(true)}
            className="btn-ghost px-2.5 py-1.5 text-xs"
            style={{ color: 'var(--color-ai)' }}
          >
            + 发布事件
          </button>
          <button onClick={refreshEvents} className="btn-ghost px-2 py-1.5 text-xs" title="刷新">
            <Icon><polyline points="23 4 23 10 17 10" /><path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15" /></Icon>
          </button>
        </div>
      </div>

      {loadingEvents ? (
        <p className="text-xs text-center py-6" style={{ color: 'var(--text-muted)' }}>加载中…</p>
      ) : error ? (
        <div
          className="rounded-[var(--radius-md)] p-2.5 text-xs"
          style={{
            backgroundColor: 'color-mix(in srgb, var(--color-error) 12%, transparent)',
            border: '1px solid var(--color-error)',
            color: 'var(--color-error)',
          }}
        >
          加载失败: {error}
        </div>
      ) : events.length === 0 ? (
        <EmptyState title="暂无事件" description="点击右上角发布事件或等待服务自动触发" />
      ) : (
        <div className="space-y-1.5 max-h-[600px] overflow-y-auto">
          {events.map(ev => (
            <EventRow key={ev.id} event={ev} statusColor={colors[STATUS_TOKEN[ev.status]] || 'var(--text-muted)'} />
          ))}
        </div>
      )}

      {showPublish && (
        <PublishEventDialog
          onClose={() => setShowPublish(false)}
          onPublish={async (req) => {
            try {
              await publishEvent(req);
              flash('ok', '事件已发布');
              setShowPublish(false);
            } catch (e: any) {
              flash('err', e?.message || String(e));
            }
          }}
        />
      )}

      {toast && (
        <div
          className="fixed bottom-4 left-1/2 -translate-x-1/2 px-3 py-1.5 rounded text-xs z-50"
          style={{
            backgroundColor: toast.kind === 'ok' ? 'var(--color-success)' : 'var(--color-error)',
            color: 'var(--text-on-color)',
          }}
        >
          {toast.msg}
        </div>
      )}
    </div>
  );
}

function EventRow({ event, statusColor }: { event: CgEvent; statusColor: string }) {
  return (
    <div
      className="rounded p-2 text-[10px]"
      style={{
        backgroundColor: 'var(--bg-elevated)',
        border: '1px solid var(--border-color)',
        borderLeft: `3px solid ${statusColor}`,
      }}
    >
      <div className="flex items-center justify-between mb-1">
        <div className="flex items-center gap-2">
          <span className="font-semibold" style={{ color: 'var(--text-primary)' }}>
            {EVENT_TYPE_LABELS[event.event_type]}
          </span>
          <span style={{ color: 'var(--text-muted)' }}>
            {SOURCE_LABELS[event.source_type]}: <span className="font-mono">{event.source_id}</span>
          </span>
        </div>
        <span style={{ color: statusColor }}>{event.status}</span>
      </div>
      {Object.keys(event.payload || {}).length > 0 && (
        <pre
          className="font-mono text-[9px] mt-1 p-1 rounded overflow-auto max-h-20"
          style={{ backgroundColor: 'var(--bg-hover)', color: 'var(--text-secondary)', whiteSpace: 'pre-wrap' }}
        >
          {JSON.stringify(event.payload, null, 2)}
        </pre>
      )}
      <div className="flex items-center justify-between mt-1 text-[9px]" style={{ color: 'var(--text-muted)' }}>
        <span>{event.created_at?.slice(0, 19)}</span>
        {event.processed_at && <span>处理于 {event.processed_at.slice(0, 19)}</span>}
      </div>
      {event.error_message && (
        <div
          className="text-[9px] mt-1 p-1 rounded"
          style={{
            backgroundColor: 'color-mix(in srgb, var(--color-error) 12%, transparent)',
            color: 'var(--color-error)',
          }}
        >
          {event.error_message}
        </div>
      )}
    </div>
  );
}

interface PublishEventDialogProps {
  onClose: () => void;
  onPublish: (req: {
    event_type: EventType;
    source_type: EventSourceType;
    source_id: string;
    payload?: Record<string, unknown>;
  }) => Promise<void>;
}

function PublishEventDialog({ onClose, onPublish }: PublishEventDialogProps) {
  const [eventType, setEventType] = useState<EventType>('code_push');
  const [sourceType, setSourceType] = useState<EventSourceType>('project');
  const [sourceId, setSourceId] = useState('');
  const [payloadJson, setPayloadJson] = useState('{}');
  const [err, setErr] = useState<string | null>(null);

  const submit = async () => {
    if (!sourceId.trim()) { setErr('source_id 必填'); return; }
    let payload = {};
    try { payload = JSON.parse(payloadJson || '{}'); } catch { setErr('payload 不是有效的 JSON'); return; }
    try {
      await onPublish({
        event_type: eventType,
        source_type: sourceType,
        source_id: sourceId.trim(),
        payload,
      });
    } catch (e: any) { setErr(e?.message || String(e)); }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4" style={{ backgroundColor: 'var(--bg-overlay)' }} onClick={onClose}>
      <div className="w-full max-w-md rounded-[var(--radius-md)] p-3" style={{ backgroundColor: 'var(--bg-elevated)', border: '1px solid var(--border-color)' }} onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-between mb-3">
          <span className="text-sm font-bold" style={{ color: 'var(--text-primary)' }}>发布事件</span>
          <button onClick={onClose} className="btn-ghost px-2 py-1 text-[11px]">✕</button>
        </div>
        <div className="space-y-2 text-[11px]">
          <div>
            <label className="text-[10px]" style={{ color: 'var(--text-muted)' }}>事件类型</label>
            <select value={eventType} onChange={(e) => setEventType(e.target.value as EventType)}
              className="w-full text-[11px] px-2 py-1 rounded"
              style={{ backgroundColor: 'var(--bg-hover)', color: 'var(--text-primary)', border: '1px solid var(--border-color)' }}>
              {(Object.keys(EVENT_TYPE_LABELS) as EventType[]).map(t => (
                <option key={t} value={t}>{EVENT_TYPE_LABELS[t]}</option>
              ))}
            </select>
          </div>
          <div className="grid grid-cols-2 gap-2">
            <div>
              <label className="text-[10px]" style={{ color: 'var(--text-muted)' }}>Source 类型</label>
              <select value={sourceType} onChange={(e) => setSourceType(e.target.value as EventSourceType)}
                className="w-full text-[11px] px-2 py-1 rounded"
                style={{ backgroundColor: 'var(--bg-hover)', color: 'var(--text-primary)', border: '1px solid var(--border-color)' }}>
                {(Object.keys(SOURCE_LABELS) as EventSourceType[]).map(s => (
                  <option key={s} value={s}>{SOURCE_LABELS[s]}</option>
                ))}
              </select>
            </div>
            <div>
              <label className="text-[10px]" style={{ color: 'var(--text-muted)' }}>Source ID</label>
              <input value={sourceId} onChange={(e) => setSourceId(e.target.value)}
                className="w-full text-[11px] px-2 py-1 rounded font-mono"
                style={{ backgroundColor: 'var(--bg-hover)', color: 'var(--text-primary)', border: '1px solid var(--border-color)' }} />
            </div>
          </div>
          <div>
            <label className="text-[10px]" style={{ color: 'var(--text-muted)' }}>Payload (JSON)</label>
            <textarea value={payloadJson} onChange={(e) => setPayloadJson(e.target.value)} rows={4}
              className="w-full text-[10px] px-2 py-1 rounded font-mono"
              style={{ backgroundColor: 'var(--bg-hover)', color: 'var(--text-primary)', border: '1px solid var(--border-color)' }} />
          </div>
          {err && (
            <div
              className="text-[10px]"
              style={{ color: 'var(--color-error)' }}
            >
              {err}
            </div>
          )}
          <button onClick={submit} className="btn-ghost w-full py-1.5 text-[11px]" style={{ color: 'var(--color-ai)' }}>发布</button>
        </div>
      </div>
    </div>
  );
}
