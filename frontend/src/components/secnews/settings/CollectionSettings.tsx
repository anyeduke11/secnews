/**
 * CollectionSettings — 采集源管理
 *
 * Phase 0 骨架：展示当前采集源列表（数据来自后端 sources API）。
 */
export function CollectionSettings() {
  return (
    <div className="p-3 rounded-[var(--radius-sm)]" style={{ border: '1px solid var(--border-color)' }}>
      <h3 className="text-xs font-mono font-medium mb-2" style={{ color: 'var(--text-primary)' }}>采集源管理</h3>
      <p className="text-[10px]" style={{ color: 'var(--text-muted)' }}>
        采集源配置在 Phase 1 实现。当前通过 /api/sources 管理。
      </p>
    </div>
  );
}
