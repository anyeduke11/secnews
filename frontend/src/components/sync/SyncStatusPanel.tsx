/**
 * SyncStatusPanel — 同步状态卡 (上次同步时间 / 状态 / 设备 ID / 自动同步开关)。
 *
 * Phase 1B: 拆自原 SyncPage.tsx 状态卡 (lines 303-340)。
 * 仅渲染, props-only; 数据由 index.tsx 注入。
 */
import React from 'react';
import { formatRelativeTime } from '../../types';
import { SyncStatusBadge } from './SyncStatusBadge';

export interface SyncStatus {
  configured: boolean;
  last_sync_at?: string | null;
  last_sync_status?: string | null;
  last_sync_direction?: string | null;
  auto_sync_enabled?: boolean;
  last_sync_error?: string | null;
  device_id?: string | null;
}

interface SyncStatusPanelProps {
  status: SyncStatus | null | undefined;
}

export function SyncStatusPanel({ status }: SyncStatusPanelProps) {
  if (!status?.configured || !status) return null;

  return (
    <div
      className="rounded-lg p-3 mb-3 text-xs space-y-1"
      style={{
        background: 'var(--surface-1)',
        border: '1px solid var(--border-subtle)',
      }}
    >
      <div className="flex items-center gap-2 flex-wrap">
        <span style={{ color: 'var(--text-muted)' }}>上次同步:</span>
        <span style={{ color: 'var(--text-primary)' }}>
          {status.last_sync_at
            ? formatRelativeTime(status.last_sync_at)
            : '从未'}
        </span>
        <SyncStatusBadge status={status.last_sync_status} />
        {status.last_sync_direction && (
          <span style={{ color: 'var(--text-muted)' }}>
            ({status.last_sync_direction})
          </span>
        )}
        {status.auto_sync_enabled ? (
          <span style={{ color: 'var(--color-success)' }}>· 自动同步开</span>
        ) : (
          <span style={{ color: 'var(--text-muted)' }}>· 自动同步关</span>
        )}
      </div>
      {status.last_sync_error && (
        <div className="text-[11px]" style={{ color: 'var(--color-error)' }}>
          错误: {status.last_sync_error}
        </div>
      )}
      <div className="text-[11px]" style={{ color: 'var(--text-muted)' }}>
        device_id: {status.device_id?.slice(0, 8)}…
      </div>
    </div>
  );
}
