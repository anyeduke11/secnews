/**
 * SourceItem — 单条自定义信源渲染（Phase 1B 抽出）。
 *
 * Phase 1B: 拆自 SourceSettings.tsx 中单条信源的复杂 JSX。
 * 独立可测；通过 props 接收 source 数据和 handlers。
 */
import React from 'react';

export interface SourceItemData {
  id: number;
  name: string;
  url: string;
  category: string;
  enabled: boolean;
  last_check_status?: string;
  last_check_latency_ms?: number;
}

interface SourceItemProps {
  source: SourceItemData;
  onToggle: (id: number, enabled: boolean) => void;
  onProbe: (id: number) => void;
  onDelete: (id: number) => void;
}

export function SourceItem({ source: s, onToggle, onProbe, onDelete }: SourceItemProps) {
  return (
    <div
      className="p-1.5 rounded-[var(--radius-sm)] text-[10px]"
      style={{
        backgroundColor: 'var(--bg-hover)',
        border: '1px solid var(--border-color)',
      }}
    >
      <div className="flex items-center gap-1.5">
        <span
          className="font-mono truncate flex-1"
          style={{ color: 'var(--text-primary)' }}
          title={s.url}
        >
          {s.name || s.url}
        </span>
        <span
          className="px-1 py-0.5 rounded text-[9px]"
          style={{ backgroundColor: 'var(--color-ai)', color: '#fff' }}
        >
          {s.category}
        </span>
      </div>
      <div className="text-[9px] mt-0.5" style={{ color: 'var(--text-muted)' }}>
        {s.last_check_status || '未探测'} · {Math.round(s.last_check_latency_ms || 0)}ms
      </div>
      <div className="flex gap-1 mt-1">
        <button
          onClick={() => onToggle(s.id, !s.enabled)}
          className="px-1.5 py-0.5 text-[9px] rounded"
          style={{
            backgroundColor: s.enabled ? 'var(--color-ai)' : 'var(--bg-primary)',
            color: s.enabled ? '#fff' : 'var(--text-muted)',
          }}
        >
          {s.enabled ? '启用' : '禁用'}
        </button>
        <button
          onClick={() => onProbe(s.id)}
          className="px-1.5 py-0.5 text-[9px] rounded"
          style={{
            backgroundColor: 'var(--bg-primary)',
            color: 'var(--text-secondary)',
          }}
        >
          探测
        </button>
        <button
          onClick={() => onDelete(s.id)}
          className="px-1.5 py-0.5 text-[9px] rounded"
          style={{ backgroundColor: 'var(--bg-primary)', color: '#e85d5d' }}
        >
          删除
        </button>
      </div>
    </div>
  );
}
