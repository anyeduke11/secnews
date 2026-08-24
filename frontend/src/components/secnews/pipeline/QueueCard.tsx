/**
 * QueueCard — 队列状态 + 死信表 (S1-4)
 */
interface DeadLetterRow {
  id: number;
  item_id: string;
  stage: string;
  attempts: number;
  last_error: string;
  updated_at: string;
}

interface QueueCardProps {
  queue: { pending: number; running: number; error: number };
  errors: Array<DeadLetterRow>;
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
          <h4 className="text-[10px] font-mono mb-1.5" style={{ color: 'var(--color-error)' }}>
            死信队列 ({errors.length})
          </h4>
          <table className="w-full text-[10px] font-mono" style={{ borderCollapse: 'collapse' }}>
            <thead>
              <tr style={{ color: 'var(--text-muted)', textAlign: 'left' }}>
                <th className="py-0.5 pr-2 font-normal">阶段</th>
                <th className="py-0.5 pr-2 font-normal">条目</th>
                <th className="py-0.5 pr-2 font-normal">错误</th>
                <th className="py-0.5 pr-2 font-normal text-right">重试</th>
              </tr>
            </thead>
            <tbody>
              {errors.map(e => (
                <tr key={e.id} style={{ borderTop: '1px solid var(--border-color)' }}>
                  <td className="py-1 pr-2 whitespace-nowrap" style={{ color: 'var(--color-error)' }}>
                    {e.stage.replace('kl:', '')}
                  </td>
                  <td className="py-1 pr-2 max-w-[120px] truncate" title={e.item_id} style={{ color: 'var(--text-secondary)' }}>
                    {e.item_id}
                  </td>
                  <td className="py-1 pr-2 max-w-[220px] truncate" title={e.last_error} style={{ color: 'var(--text-muted)' }}>
                    {e.last_error}
                  </td>
                  <td className="py-1 text-right tabular-nums" style={{ color: 'var(--text-secondary)' }}>
                    {e.attempts}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
