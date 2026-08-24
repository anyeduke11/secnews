/**
 * PipelineSettings — 管线参数配置
 *
 * Phase 0 骨架：展示管线参数说明。
 */
export function PipelineSettings() {
  return (
    <div className="p-3 rounded-[var(--radius-sm)]" style={{ border: '1px solid var(--border-color)' }}>
      <h3 className="text-xs font-mono font-medium mb-2" style={{ color: 'var(--text-primary)' }}>管线参数</h3>
      <div className="text-[10px] font-mono space-y-1" style={{ color: 'var(--text-muted)' }}>
        <div>阶段数: 5 (raw → refine → link → structure → publish)</div>
        <div>重试上限: 5 次</div>
        <div>Kickoff 延迟: 45s</div>
        <div>批处理大小: 20</div>
      </div>
    </div>
  );
}
