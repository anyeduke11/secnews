/**
 * TriggerTimeline — 最近触发事件时间线 (B5.6 拆分自 Dashboard)。
 *
 * 纯展示: 触发条目列表 (source + ticket_id + status 徽标 + 相对时间)。
 */
import { useI18n } from '../../contexts/I18nContext';
import { relativeTime, TRIGGER_STATUS_META } from './dashboardModel';
import type { TriggerTimelineItem } from './dashboardModel';

export function TriggerTimeline({ items }: { items: TriggerTimelineItem[] }) {
  const { t } = useI18n();
  return (
    <section
      className="rounded-md border border-[var(--sn-line,#3a3f45)] bg-[var(--sn-bg-1,#101316)] p-4"
      data-testid="trigger-timeline"
      aria-label="trigger timeline"
    >
      <h2 className="text-[13px] font-medium mb-3" data-testid="trigger-timeline-title">
        {t('dashboard.timeline.title', '触发器时间线')} · {items.length}
      </h2>
      <ol className="space-y-2" data-testid="trigger-timeline-list">
        {items.map(item => (
          <li
            key={item.ticket_id}
            className="flex items-center justify-between text-[12px] border-b border-[var(--sn-line,#3a3f45)]/40 py-2"
            data-testid={`trigger-timeline-row-${item.ticket_id}`}
          >
            <span className="font-mono text-[var(--sn-ink-3,#8a929c)]">{item.ticket_id}</span>
            <span className="px-2 text-[11px] font-mono" data-testid="trigger-source">
              {item.source}
            </span>
            <span className="font-mono">{item.target_id}</span>
            <StatusBadge status={item.status} />
            <span className="text-[var(--sn-ink-3,#8a929c)] font-mono tabular-nums">
              {relativeTime(item.created_at)}
            </span>
          </li>
        ))}
      </ol>
    </section>
  );
}

function StatusBadge({ status }: { status: TriggerTimelineItem['status'] }) {
  const meta = TRIGGER_STATUS_META[status];
  return (
    <span
      className="rounded px-1.5 py-0.5 text-[11px] font-mono"
      style={{ background: 'var(--sn-bg-2,#15181d)', color: meta.color }}
      data-testid={`trigger-status-${status}`}
    >
      {meta.label}
    </span>
  );
}
