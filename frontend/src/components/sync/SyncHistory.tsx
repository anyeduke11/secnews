/**
 * SyncHistory — 同步历史列表 + 冲突裁决区。
 *
 * Phase 1B: 拆自原 SyncPage.tsx 冲突裁决 (lines 716-802) + 历史 (lines 804-847)。
 * 包含冲突表列表 (保留本地/远端) 与最近 N 条同步历史。
 * 仅渲染, props-only; 数据与回调由 index.tsx 注入。
 */
import React from 'react';
import { formatRelativeTime } from '../../types';
import { SyncStatusBadge } from './SyncStatusBadge';
import type { ConflictInfo, HistoryItem } from './types';

export type { ConflictInfo, HistoryItem };

interface SyncHistoryProps {
  configured: boolean;
  history: HistoryItem[];
  conflicts: ConflictInfo | null;
  onResolveConflict: (table: string, choice: 'local' | 'remote') => void;
}

const TABLE_LABELS: Record<string, string> = {
  favorites: '收藏',
  todos: '待办',
  skills: 'Skill',
  custom_sources: '自定义源',
  secrets: '密钥',
};

export function SyncHistory({
  configured,
  history,
  conflicts,
  onResolveConflict,
}: SyncHistoryProps) {
  return (
    <>
      {/* 冲突裁决 */}
      {configured && conflicts && conflicts.total > 0 && (
        <div
          className="rounded-lg p-4 mb-3"
          style={{
            background: 'color-mix(in srgb, var(--color-warning) 5%, transparent)',
            border: '1px solid color-mix(in srgb, var(--color-warning) 30%, transparent)',
          }}
        >
          <h3 className="text-sm font-semibold mb-2" style={{ color: 'var(--color-warning)' }}>
            同步冲突 ({conflicts.total} 项)
          </h3>
          <p className="text-[11px] mb-2" style={{ color: 'var(--text-muted)' }}>
            以下表存在本地与远端冲突，请选择保留本地或远端版本。
          </p>
          <div className="space-y-1.5">
            {Object.entries(conflicts.conflicts).map(([table, count]) => (
              <div
                key={table}
                className="flex items-center justify-between text-xs px-2 py-1.5 rounded"
                style={{ background: 'var(--surface-2)' }}
              >
                <span style={{ color: 'var(--text-primary)' }}>
                  {TABLE_LABELS[table] || table}
                </span>
                <div className="flex items-center gap-2">
                  <span style={{ color: 'var(--color-warning)' }}>{count} 项冲突</span>
                  <button
                    className="text-[10px] px-2 py-0.5 rounded font-medium"
                    style={{
                      background: 'color-mix(in srgb, var(--color-error) 20%, transparent)',
                      color: 'var(--color-error)',
                      border: '1px solid color-mix(in srgb, var(--color-error) 30%, transparent)',
                    }}
                    onClick={() => onResolveConflict(table, 'local')}
                  >
                    保留本地
                  </button>
                  <button
                    className="text-[10px] px-2 py-0.5 rounded font-medium"
                    style={{
                      background: 'color-mix(in srgb, var(--color-info) 20%, transparent)',
                      color: 'var(--color-info)',
                      border: '1px solid color-mix(in srgb, var(--color-info) 30%, transparent)',
                    }}
                    onClick={() => onResolveConflict(table, 'remote')}
                  >
                    保留远端
                  </button>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* 历史 */}
      {history.length > 0 && (
        <div
          className="rounded-lg p-4"
          style={{
            background: 'var(--surface-1)',
            border: '1px solid var(--border-subtle)',
          }}
        >
          <h3 className="text-sm font-semibold mb-3" style={{ color: 'var(--text-primary)' }}>
            同步历史 (最近 {history.length} 条)
          </h3>
          <div className="space-y-1.5">
            {history.map(h => (
              <div
                key={h.id}
                className="flex items-center gap-2 text-[11px] flex-wrap px-2 py-1.5 rounded"
                style={{ background: 'var(--surface-2)' }}
              >
                <SyncStatusBadge status={h.status} />
                <span style={{ color: 'var(--text-primary)' }}>{h.direction}</span>
                <span style={{ color: 'var(--text-muted)' }}>
                  {formatRelativeTime(h.started_at)}
                </span>
                {h.records_count != null && (
                  <span style={{ color: 'var(--text-muted)' }}>
                    {h.records_count} 条
                  </span>
                )}
                {(h.conflict_count ?? 0) > 0 && (
                  <span style={{ color: 'var(--color-warning)' }}>
                    冲突 {h.conflict_count}
                  </span>
                )}
                {h.error_message && (
                  <span style={{ color: 'var(--color-error)' }} className="truncate max-w-[400px]">
                    {h.error_message}
                  </span>
                )}
              </div>
            ))}
          </div>
        </div>
      )}
    </>
  );
}
