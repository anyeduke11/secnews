/**
 * ResourceCard — 通用资源卡片（domain / env_template / volume 三种 type）。
 *
 * Phase 1B: 拆自原 ResourceHub.tsx ResourceCard 段。
 * props-only: 接收 resource + 可选 onRemove, 渲染状态徽标 + owner 元数据。
 */
import { CgResource, RESOURCE_TYPE_LABELS } from '../../../types/codegarden';
import { ResourceCardProps, PORT_STATUS_COLORS } from './types';

export function ResourceCard({ resource, onRemove }: ResourceCardProps) {
  const statusColor = PORT_STATUS_COLORS[resource.status];

  return (
    <div
      className="rounded-[var(--radius-sm)] p-2.5"
      style={{
        backgroundColor: 'var(--bg-elevated)',
        border: '1px solid var(--border-color)',
        borderLeft: `3px solid ${statusColor}`,
      }}
    >
      <div className="flex items-start justify-between gap-2">
        <div className="flex-1 min-w-0">
          <div
            className="text-xs font-semibold truncate font-mono"
            style={{ color: 'var(--text-primary)' }}
            title={resource.value}
          >
            {resource.value}
          </div>
          <div className="text-[10px] mt-0.5" style={{ color: 'var(--text-muted)' }}>
            {RESOURCE_TYPE_LABELS[resource.type]}
          </div>
        </div>
        <span
          className="shrink-0 text-[9px] px-1.5 py-0.5 rounded"
          style={{ backgroundColor: statusColor + '20', color: statusColor }}
        >
          {resource.status}
        </span>
      </div>
      {resource.owner_service_id && (
        <div className="text-[10px] mt-1.5" style={{ color: 'var(--text-muted)' }}>
          ↳ service: <span className="font-mono">{resource.owner_service_id}</span>
        </div>
      )}
      {resource.owner_project_id && (
        <div className="text-[10px]" style={{ color: 'var(--text-muted)' }}>
          ↳ project: <span className="font-mono">{resource.owner_project_id}</span>
        </div>
      )}
      {resource.reserved_until && (
        <div className="text-[10px]" style={{ color: 'var(--text-muted)' }}>
          预留至: {resource.reserved_until.slice(0, 19)}
        </div>
      )}
      {onRemove && (
        <button
          onClick={async () => {
            try {
              await onRemove();
            } catch (e: any) {
              window.alert(e?.message || String(e));
            }
          }}
          className="mt-2 text-[9px] w-full py-0.5 rounded"
          style={{ border: '1px solid var(--border-color)', color: 'var(--color-error)' }}
        >
          删除
        </button>
      )}
    </div>
  );
}
