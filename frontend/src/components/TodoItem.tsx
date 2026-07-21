import React from 'react';
import {
  TodoItem as TodoItemModel,
  getCategoryColor,
  getCategoryLabel,
} from '../types';

interface TodoItemProps {
  item: TodoItemModel;
  onToggleDone: (id: number) => void;
  onDelete: (id: number) => void;
  /** Phase 46: 只 toggle 重要, 紧急由 deadline 派生。 */
  onImportantToggle: (id: number, important: boolean) => void;
  /** Phase 46: 截止日期变更 (清空 = null)。 */
  onDeadlineChange: (id: number, deadline: string | null) => void;
}

// 4 象限视觉配置 (Eisenhower Matrix)
type Quadrant = 'P0' | 'P1' | 'P2' | 'P3';
const QUADRANT_INFO: Record<Quadrant, { color: string; bg: string; label: string; symbol: string }> = {
  P0: { color: 'var(--color-error)', bg: 'var(--color-error)', label: '紧急+重要', symbol: '🔴' },
  P1: { color: 'var(--color-bid)', bg: 'var(--color-bid)', label: '紧急+不重要', symbol: '🟠' },
  P2: { color: 'var(--color-info)', bg: 'var(--color-info)', label: '不紧急+重要', symbol: '🔵' },
  P3: { color: 'var(--text-muted)', bg: 'transparent', label: '不紧急+不重要', symbol: '⚪' },
};

function getQuadrant(urgent: boolean, important: boolean): Quadrant {
  if (urgent && important) return 'P0';
  if (urgent && !important) return 'P1';
  if (!urgent && important) return 'P2';
  return 'P3';
}

// 复用项目 14×14 stroke=2 strokeLinecap=round 风格
function Icon({ children, size = 14 }: { children: React.ReactNode; size?: number }) {
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

// Phase 46: 截止日期展示
// - 过期 (deadline < today) → 红色
// - 今天/明天 (≤1 业务日) → 红色加粗
// - 周末 (deadline 在 Sat/Sun) → 「顺延到下周一」 提示
// - 远期 (>1 业务日) → 普通
function formatDeadline(
  deadline: string | null,
  urgent: boolean,
): { text: string; title: string; color: string; weight: 'normal' | 'bold' } {
  if (!deadline) {
    return {
      text: '无截止',
      title: '未设置截止日期 (永远不紧急)',
      color: 'var(--text-muted)',
      weight: 'normal',
    };
  }
  // deadline 是 'YYYY-MM-DD', 本地解析
  const d = new Date(deadline + 'T00:00:00');
  if (Number.isNaN(d.getTime())) {
    return { text: deadline, title: deadline, color: 'var(--text-muted)', weight: 'normal' };
  }
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  const diffMs = d.getTime() - today.getTime();
  const diffDays = Math.round(diffMs / 86_400_000);
  const isWeekend = d.getDay() === 0 || d.getDay() === 6;

  let label: string;
  if (diffDays < 0) {
    label = `已过期 ${-diffDays} 天`;
  } else if (diffDays === 0) {
    label = '今天';
  } else if (diffDays === 1) {
    label = '明天';
  } else if (diffDays < 7) {
    label = `${diffDays} 天后`;
  } else {
    label = d.toLocaleDateString('zh-CN', { month: 'numeric', day: 'numeric' });
  }

  if (urgent) {
    return {
      text: `⚡ ${label}`,
      title: `${deadline} (自动判断为紧急: ≤1 业务日, 过滤周末)${isWeekend ? ' — 截止落在周末, 顺延到下周一' : ''}`,
      color: 'var(--color-error)',
      weight: 'bold',
    };
  }
  return {
    text: `📅 ${label}`,
    title: `${deadline} (非紧急: >1 业务日)${isWeekend ? ' — 截止落在周末, 顺延到下周一' : ''}`,
    color: 'var(--text-secondary)',
    weight: 'normal',
  };
}

export function TodoItem({
  item,
  onToggleDone,
  onDelete,
  onImportantToggle,
  onDeadlineChange,
}: TodoItemProps) {
  const isDone = item.status === 'done';
  const isArchived = item.status === 'archived';
  const quadrant = getQuadrant(item.urgent, item.important);
  const qInfo = QUADRANT_INFO[quadrant];
  const catColor = item.category ? getCategoryColor(item.category) : 'var(--text-muted)';
  const deadlineInfo = formatDeadline(item.deadline, item.urgent);

  const handleToggleClick = () => {
    onToggleDone(item.id);
  };

  const handleImportantClick = () => {
    if (isArchived) return;
    // Phase 46: 只 toggle 重要, 紧急由 deadline 派生
    onImportantToggle(item.id, !item.important);
  };

  const handleDeadlineEdit = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (isArchived) return;
    const v = e.target.value;
    onDeadlineChange(item.id, v || null);
  };

  const handleDeleteClick = () => {
    onDelete(item.id);
  };

  return (
    <div
      className="flex items-center gap-3 px-3.5"
      style={{
        // Phase 36 UI 2: 卡片改成长方形铅笔线条风格, 固定 80px 高度便于扫读
        height: 80,
        backgroundColor: 'var(--bg-card)',
        // 4 边 1.5px 深色细线 + 左侧 4px 优先级色 accent (长方形但保留象限识别)
        border: `1.5px solid ${isDone ? 'var(--border-color)' : 'var(--text-secondary)'}`,
        borderLeft: `4px solid ${qInfo.color}`,
        borderRadius: 6,
        // 极轻 outer shadow + 极轻 inner 模拟纸片感
        boxShadow: isDone
          ? 'inset 0 1px 2px rgba(0,0,0,0.04)'
          : '0 1px 0 rgba(0,0,0,0.04), inset 0 1px 0 rgba(255,255,255,0.6)',
        opacity: isArchived ? 0.55 : 1,
        transition: 'all 160ms ease',
      }}
    >
      {/* 左侧: 圆形 checkbox */}
      <button
        type="button"
        onClick={handleToggleClick}
        disabled={isArchived}
        className="shrink-0 rounded-full focus-ring transition-colors"
        style={{
          width: 20,
          height: 20,
          border: `2px solid ${isDone ? 'var(--color-general)' : 'var(--border-color)'}`,
          backgroundColor: isDone ? 'var(--color-general)' : 'transparent',
          color: isDone ? 'var(--text-on-light)' : 'transparent',
          cursor: isArchived ? 'not-allowed' : 'pointer',
          display: 'inline-flex',
          alignItems: 'center',
          justifyContent: 'center',
        }}
        title={isArchived ? '已归档' : isDone ? '标记为未完成' : '标记为已完成'}
        aria-label={isDone ? '标记为未完成' : '标记为已完成'}
        aria-pressed={isDone}
      >
        {isDone && (
          <Icon size={12}>
            <polyline points="20 6 9 17 4 12" />
          </Icon>
        )}
      </button>

      {/* 中间: 标题 + 分类徽标 + 信源 + note + 截止日期 (单行 truncate 避免超高) */}
      <div className="flex-1 min-w-0 flex flex-col gap-1 justify-center">
        <h3
          className="text-[13px] font-medium leading-tight truncate"
          style={{
            color: isDone ? 'var(--text-muted)' : 'var(--text-primary)',
            textDecoration: isDone ? 'line-through' : 'none',
          }}
          title={item.title}
        >
          {item.title}
        </h3>

        <div className="flex items-center gap-1.5 flex-wrap text-[10px]">
          {item.category && (
            <span
              className="badge"
              style={{
                backgroundColor: `${catColor}14`,
                color: catColor,
              }}
            >
              {getCategoryLabel(item.category)}
            </span>
          )}
          {item.source && (
            <span
              className="truncate max-w-[200px]"
              style={{ color: 'var(--text-muted)' }}
              title={item.source}
            >
              {item.source}
            </span>
          )}
          {/* Phase 46: 截止日期 badge — 紧急时变红加粗, 否则普通色 */}
          {item.deadline && (
            <span
              style={{ color: deadlineInfo.color, fontWeight: deadlineInfo.weight }}
              title={deadlineInfo.title}
            >
              {deadlineInfo.text}
            </span>
          )}
          {item.note && (
            <span
              className="truncate max-w-[240px] italic"
              style={{ color: 'var(--text-secondary)' }}
              title={item.note}
            >
              · {item.note}
            </span>
          )}
        </div>
      </div>

      {/* 右侧: 重要切换 + 截止日期编辑 + 4 象限 chip + 打开原文 + 删除 */}
      <div className="shrink-0 flex items-center gap-1.5">
        {/* Phase 46: 重要切换按钮 (替代旧的 4 象限循环) */}
        <button
          type="button"
          onClick={handleImportantClick}
          disabled={isArchived}
          className="px-1.5 py-0.5 rounded-[var(--radius-sm)] text-[10px] focus-ring"
          style={{
            border: `1px solid ${item.important ? 'var(--color-info)' : 'var(--border-color)'}`,
            backgroundColor: item.important ? 'color-mix(in srgb, var(--color-info) 8%, transparent)' : 'transparent',
            color: item.important ? 'var(--color-info)' : 'var(--text-muted)',
            cursor: isArchived ? 'not-allowed' : 'pointer',
          }}
          title={item.important ? '取消重要' : '标记为重要'}
          aria-label={item.important ? '取消重要' : '标记为重要'}
        >
          {item.important ? '★ 重要' : '☆ 标为重要'}
        </button>

        {/* Phase 46: 截止日期快速编辑 (input type=date, 仅图标) */}
        <label
          className="btn-ghost p-1.5"
          style={{
            minHeight: 0,
            cursor: isArchived ? 'not-allowed' : 'pointer',
            opacity: isArchived ? 0.4 : 1,
            position: 'relative',  // input 绝对定位的参照
          }}
          title={item.deadline ? `截止: ${item.deadline}` : '设置截止日期'}
        >
          <Icon>
            <rect x="3" y="4" width="18" height="18" rx="2" />
            <line x1="16" y1="2" x2="16" y2="6" />
            <line x1="8" y1="2" x2="8" y2="6" />
            <line x1="3" y1="10" x2="21" y2="10" />
          </Icon>
          <input
            type="date"
            value={item.deadline || ''}
            onChange={handleDeadlineEdit}
            disabled={isArchived}
            // 覆盖整个 label 区域: 点击图标实际是点击 input, 浏览器自动弹 date picker
            style={{
              position: 'absolute',
              top: 0,
              left: 0,
              width: '100%',
              height: '100%',
              opacity: 0,
              cursor: isArchived ? 'not-allowed' : 'pointer',
              border: 'none',
              background: 'transparent',
              padding: 0,
              margin: 0,
            }}
          />
        </label>

        {/* 4 象限 chip (read-only, 反映 effective_urgent × important) */}
        <div
          style={{
            width: 18,
            height: 18,
            borderRadius: '50%',
            backgroundColor: qInfo.bg,
            border: quadrant === 'P3' ? '2px solid var(--text-muted)' : 'none',
            display: 'inline-flex',
            alignItems: 'center',
            justifyContent: 'center',
            opacity: isArchived ? 0.6 : 1,
          }}
          title={`${qInfo.label} (紧急由截止日期自动判断)`}
          aria-label={`象限: ${qInfo.label}`}
        >
          {quadrant === 'P3' && (
            <span
              style={{
                width: 5,
                height: 5,
                borderRadius: '50%',
                backgroundColor: 'var(--text-muted)',
              }}
            />
          )}
        </div>

        {item.url && (
          <a
            href={item.url}
            target="_blank"
            rel="noopener noreferrer"
            className="btn-ghost p-1.5"
            style={{ minHeight: 0 }}
            title="打开原文"
            aria-label="打开原文"
          >
            <Icon>
              <path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6" />
              <polyline points="15 3 21 3 21 9" />
              <line x1="10" y1="14" x2="21" y2="3" />
            </Icon>
          </a>
        )}

        <button
          type="button"
          onClick={handleDeleteClick}
          className="btn-ghost p-1.5 transition-colors"
          style={{ minHeight: 0, color: 'var(--text-muted)' }}
          title="删除"
          aria-label="删除"
          onMouseEnter={e => {
            (e.currentTarget as HTMLElement).style.color = 'var(--color-error)';
            (e.currentTarget as HTMLElement).style.borderColor = 'var(--color-error)';
          }}
          onMouseLeave={e => {
            (e.currentTarget as HTMLElement).style.color = 'var(--text-muted)';
            (e.currentTarget as HTMLElement).style.borderColor = 'var(--border-color)';
          }}
        >
          <Icon>
            <polyline points="3 6 5 6 21 6" />
            <path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6" />
            <path d="M10 11v6" />
            <path d="M14 11v6" />
            <path d="M9 6V4a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v2" />
          </Icon>
        </button>
      </div>
    </div>
  );
}
