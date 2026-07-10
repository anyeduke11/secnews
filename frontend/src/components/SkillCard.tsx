import React, { useState } from 'react';
import { SkillItem } from '../types';

interface SkillCardProps {
  item: SkillItem;
  onEdit?: (item: SkillItem) => void;
  onDelete?: (id: number) => void;
}

function Icon({ children, size = 12 }: { children: React.ReactNode; size?: number }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      {children}
    </svg>
  );
}

const SOURCE_COLOR: Record<string, string> = {
  npx: '#7c6aff',
  uvx: '#00bcd4',
  curl: '#e8891a',
  git: '#e85d5d',
  manual: '#888899',
};

export function SkillCard({ item, onEdit, onDelete }: SkillCardProps) {
  const [copied, setCopied] = useState(false);

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(item.install_command);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1500);
    } catch (e) {
      // 退路: 选中文本让用户手动复制
      console.error('clipboard write failed:', e);
      try {
        const ta = document.createElement('textarea');
        ta.value = item.install_command;
        ta.style.position = 'fixed';
        ta.style.left = '-9999px';
        document.body.appendChild(ta);
        ta.select();
        document.execCommand('copy');
        document.body.removeChild(ta);
        setCopied(true);
        window.setTimeout(() => setCopied(false), 1500);
      } catch {
        // 静默
      }
    }
  };

  const sourceColor = SOURCE_COLOR[item.source] || SOURCE_COLOR.manual;

  return (
    <div
      className="rounded-[var(--radius-md)] p-3 flex flex-col gap-2"
      style={{
        backgroundColor: 'var(--bg-elevated)',
        border: '1px solid var(--border-color)',
      }}
    >
      {/* 顶部: 名称 + source 标签 + 操作按钮 */}
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-2 min-w-0 flex-1">
          <h3
            className="text-sm font-bold truncate"
            style={{ color: 'var(--text-primary)' }}
            title={item.name}
          >
            {item.name}
          </h3>
          <span
            className="text-[10px] font-mono px-1.5 py-0.5 rounded-[var(--radius-sm)] shrink-0"
            style={{ backgroundColor: `${sourceColor}22`, color: sourceColor, border: `1px solid ${sourceColor}55` }}
          >
            {item.source}
          </span>
        </div>
        <div className="flex items-center gap-1 shrink-0">
          {onEdit && (
            <button
              onClick={() => onEdit(item)}
              className="btn-ghost px-1.5 py-0.5 text-[10px]"
              title="编辑"
              aria-label="编辑"
            >
              <Icon>
                <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7" />
                <path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z" />
              </Icon>
            </button>
          )}
          {onDelete && (
            <button
              onClick={() => {
                if (window.confirm(`确定删除「${item.name}」?`)) {
                  onDelete(item.id);
                }
              }}
              className="btn-ghost px-1.5 py-0.5 text-[10px]"
              title="删除"
              aria-label="删除"
              style={{ color: '#e85d5d' }}
            >
              <Icon>
                <polyline points="3 6 5 6 21 6" />
                <path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6" />
                <path d="M10 11v6M14 11v6" />
              </Icon>
            </button>
          )}
        </div>
      </div>

      {/* 描述 */}
      {item.description && (
        <p
          className="text-xs leading-relaxed"
          style={{ color: 'var(--text-secondary)' }}
        >
          {item.description}
        </p>
      )}

      {/* 链接 */}
      <a
        href={item.url}
        target="_blank"
        rel="noreferrer"
        className="text-[11px] truncate block hover:underline"
        style={{ color: 'var(--color-ai)' }}
        title={item.url}
      >
        🔗 {item.url}
      </a>

      {/* 安装指令块 + 复制按钮 */}
      <div
        className="flex items-stretch gap-1 rounded-[var(--radius-sm)] overflow-hidden"
        style={{ backgroundColor: 'var(--bg-card)', border: '1px solid var(--border-color)' }}
      >
        <code
          className="flex-1 px-2 py-1.5 text-[11px] font-mono overflow-x-auto whitespace-pre"
          style={{ color: 'var(--text-primary)' }}
        >
          {item.install_command}
        </code>
        <button
          onClick={handleCopy}
          className="px-2 shrink-0 text-[10px] font-bold transition-colors"
          style={{
            backgroundColor: copied ? '#00c96a' : 'var(--bg-hover)',
            color: copied ? '#fff' : 'var(--text-primary)',
            borderLeft: '1px solid var(--border-color)',
            minWidth: 56,
          }}
          title={copied ? '已复制' : '复制安装指令'}
          aria-label="复制"
        >
          {copied ? '✓ 已复制' : '📋 复制'}
        </button>
      </div>

      {/* 标签 */}
      {item.tags && item.tags.length > 0 && (
        <div className="flex items-center gap-1 flex-wrap">
          {item.tags.map(tag => (
            <span
              key={tag}
              className="text-[10px] font-mono px-1.5 py-0.5 rounded-[var(--radius-sm)]"
              style={{
                backgroundColor: 'var(--bg-hover)',
                color: 'var(--text-muted)',
                border: '1px solid var(--border-color)',
              }}
            >
              #{tag}
            </span>
          ))}
        </div>
      )}
    </div>
  );
}
