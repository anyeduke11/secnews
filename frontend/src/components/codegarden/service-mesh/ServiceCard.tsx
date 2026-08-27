/**
 * ServiceCard — 单个服务卡片（runtime/status/type/port 徽标 + 依赖数）。
 *
 * Phase 1B: 拆自原 ServiceMesh.tsx ServiceCard。
 * props-only: 接收 service + onClick, 完全无业务状态。
 */
import { SERVICE_RUNTIME_COLORS, SERVICE_STATUS_COLORS } from '../../../types/codegarden';
import { ServiceCardProps, STATUS_LABELS } from './types';

export function ServiceCard({ service, onClick }: ServiceCardProps) {
  const runtimeColor = SERVICE_RUNTIME_COLORS[service.runtime];
  const statusColor = SERVICE_STATUS_COLORS[service.status];

  return (
    <div
      onClick={onClick}
      className="rounded-[var(--radius-sm)] p-2.5 cursor-pointer transition-colors"
      style={{
        backgroundColor: 'var(--bg-elevated)',
        border: '1px solid var(--border-color)',
        borderLeft: `3px solid ${statusColor}`,
      }}
    >
      <div className="flex items-start justify-between gap-2">
        <div className="flex-1 min-w-0">
          <div
            className="text-xs font-semibold truncate"
            style={{ color: 'var(--text-primary)' }}
            title={service.name}
          >
            {service.name}
          </div>
          {service.namespace && (
            <div className="text-[10px] mt-0.5" style={{ color: 'var(--text-muted)' }}>
              {service.namespace}
            </div>
          )}
        </div>
        <span
          className="shrink-0 text-[10px] px-1.5 py-0.5 rounded"
          style={{ backgroundColor: statusColor + '20', color: statusColor }}
        >
          {STATUS_LABELS[service.status]}
        </span>
      </div>

      <div className="flex items-center gap-1.5 mt-2 flex-wrap">
        <span
          className="text-[10px] px-1.5 py-0.5 rounded"
          style={{ backgroundColor: runtimeColor + '20', color: runtimeColor }}
        >
          {service.runtime}
        </span>
        <span
          className="text-[10px] px-1.5 py-0.5 rounded"
          style={{ backgroundColor: 'var(--bg-hover)', color: 'var(--text-secondary)' }}
        >
          {service.type}
        </span>
        {/* P5-4: 校验状态徽标 — auto=扫描发现 / manual=用户确认 */}
        <span
          className="text-[10px] px-1.5 py-0.5 rounded"
          style={{
            backgroundColor: service.discovery_source === 'manual'
              ? 'color-mix(in srgb, var(--color-success) 15%, transparent)'
              : 'var(--bg-hover)',
            color: service.discovery_source === 'manual'
              ? 'var(--color-success)'
              : 'var(--text-muted)',
          }}
          title={service.discovery_source === 'manual' ? '用户手动登记' : '扫描自动发现 (未人工确认)'}
        >
          {service.discovery_source === 'manual' ? '✓ 已确认' : '自动'}
        </span>
        {service.endpoint_port && (
          <span
            className="text-[10px] font-mono tabular-nums px-1.5 py-0.5 rounded"
            style={{ backgroundColor: 'var(--bg-hover)', color: 'var(--text-secondary)' }}
          >
            :{service.endpoint_port}
          </span>
        )}
        {service.endpoint_domain && (
          <span
            className="text-[10px] truncate max-w-[100px]"
            style={{ color: 'var(--text-muted)' }}
            title={service.endpoint_domain}
          >
            {service.endpoint_domain}
          </span>
        )}
      </div>

      {service.dependencies && service.dependencies.length > 0 && (
        <div className="text-[10px] mt-1.5" style={{ color: 'var(--text-muted)' }}>
          ↳ 依赖 {service.dependencies.length} 项
        </div>
      )}
    </div>
  );
}
