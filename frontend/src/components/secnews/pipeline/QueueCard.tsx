/**
 * QueueCard — 队列状态 + 死信列表
 */
interface QueueCardProps {
  queue: { pending: number; running: number; error: number };
  errors: Array<{ id: number; item_id: string; stage: string; last_error: string }>;
}

export function QueueCard({ queue, errors }: QueueCardProps) {
  return (
    <div className="p-3 rounded-[var(--radius-sm)]" style={{ border: '1px solid var(--border-color)' }}>
      <h3 className="text-xs font-mono font-medium mb-2" style={{ color: 'var(--text-primary)' }}>
        队列状态
      </h3>
      <div className="flex items-center gap-4 mb-3">
        {[
          { label: '待处理', value: queue.pending, color: 'var(--color-info)' },
          { label: '运行中', value: queue.running, color: 'var(--color-warning)' },
          { label: '失败', value: queue.error, color: 'var(--color-error)' },
        ].map(s => (
          <div key={s.label} className="flex items-center gap-1.5">
            <div className="w-2 h-2 rounded-full" style={{ backgroundColor: s.color }} />
            <span className="text-xs" style={{ color: 'var(--text-muted)' }}>{s.label}</span>
            <span className="text-xs font-mono font-medium tabular-nums" style={{ color: 'var(--text-primary)' }}>
              {s.value}
            </span>
          </div>
        ))}
      </div>
      {errors.length > 0 && (
        <div className="border-t pt-2" style={{ borderColor: 'var(--border-color)' }}>
          <h4 className="text-[10px] font-mono mb-1" style={{ color: 'var(--color-error)' }}>最近错误</h4>
          {errors.slice(0, 5).map(e => (
            <div key={e.id} className="text-[10px] font-mono py-0.5 truncate" style={{ color: 'var(--text-muted)' }}>
              [{e.stage}] {e.item_id}: {e.last_error}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
