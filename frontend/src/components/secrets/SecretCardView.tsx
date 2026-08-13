/**
 * secrets/SecretCardView — 单条密钥卡片。
 *
 * 拆自原 SecretsPage.tsx (794 行) 中 SecretCardView (~369-458 行)。
 * 纯结构拆分, 渲染逻辑逐字迁移。
 */
import React from 'react';
import { SecretItem } from '../../types';
import { Icon } from '../Icon';

export function SecretCardView({
  item, onEdit, onDelete, onCopy, onTest,
}: {
  item: SecretItem;
  onEdit: () => void;
  onDelete: () => void;
  onCopy: () => void;
  onTest: () => void;
}) {
  return (
    <div
      className="rounded-[var(--radius-md)] p-3 flex flex-col gap-2"
      style={{ backgroundColor: 'var(--bg-elevated)', border: '1px solid var(--border-color)' }}
    >
      {/* 头部 */}
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-2 min-w-0 flex-1">
          <h3 className="text-sm font-bold truncate" style={{ color: 'var(--text-primary)' }} title={item.name}>
            {item.name}
          </h3>
          <span
            className="text-[10px] font-mono px-1.5 py-0.5 rounded-[var(--radius-sm)] shrink-0"
            style={{ backgroundColor: 'var(--bg-hover)', color: 'var(--text-muted)' }}
          >
            {item.model}
          </span>
        </div>
        <div className="flex items-center gap-1 shrink-0">
          <button onClick={onEdit} className="btn-ghost px-1.5 py-0.5 text-[10px]" title="编辑" aria-label="编辑">
            <Icon>
              <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7" />
              <path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z" />
            </Icon>
          </button>
          <button onClick={onDelete} className="btn-ghost px-1.5 py-0.5 text-[10px]" title="删除" aria-label="删除" style={{ color: 'var(--color-error)' }}>
            <Icon>
              <polyline points="3 6 5 6 21 6" />
              <path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6" />
              <path d="M10 11v6M14 11v6" />
            </Icon>
          </button>
        </div>
      </div>

      <a
        href={item.base_url}
        target="_blank"
        rel="noreferrer"
        className="text-[11px] truncate block hover:underline"
        style={{ color: 'var(--color-ai)' }}
        title={item.base_url}
      >
        🔗 {item.base_url}
      </a>

      <div
        className="px-2 py-1.5 rounded-[var(--radius-sm)] font-mono text-[11px] overflow-x-auto"
        style={{ backgroundColor: 'var(--bg-card)', border: '1px solid var(--border-color)', color: 'var(--text-muted)' }}
      >
        {item.api_key_masked}
      </div>

      <div className="flex items-center gap-1.5 flex-wrap">
        <button
          onClick={onCopy}
          disabled={!item.unlocked}
          className="btn-ghost px-2.5 py-1 text-[11px]"
          style={{
            opacity: item.unlocked ? 1 : 0.5,
            cursor: item.unlocked ? 'pointer' : 'not-allowed',
            color: item.unlocked ? 'var(--color-ai)' : undefined,
            borderColor: item.unlocked ? 'var(--color-ai)' : undefined,
          }}
          title={item.unlocked ? '复制明文到剪贴板' : '未解锁, 无法复制'}
        >
          📋 复制
        </button>
        <button
          onClick={onTest}
          disabled={!item.unlocked}
          className="btn-ghost px-2.5 py-1 text-[11px]"
          style={{ opacity: item.unlocked ? 1 : 0.5, cursor: item.unlocked ? 'pointer' : 'not-allowed' }}
          title="测试连通性"
        >
          ⚡ 测试
        </button>
      </div>
    </div>
  );
}
