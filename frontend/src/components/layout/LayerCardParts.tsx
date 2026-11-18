/**
 * LayerCardParts — 从 layout/LayerCard.tsx 拆出的卡片内部零件 (B6-a 纯搬迁, 无行为变更)。
 * 职责: LayerCardRow / LayerCardGrid / LayerCardAlert / PipelineFlow。
 * 导出面仍由 ./LayerCard 按原名 re-export, 调用方无需改动。
 */
import React from 'react';

/**
 * LayerCardRow — 卡片内的行项目（统一 hover 状态）
 */
export function LayerCardRow({
  label, value, onClick, color, children,
}: {
  label?: string;
  value?: string | number;
  onClick?: () => void;
  color?: string;
  children?: React.ReactNode;
}) {
  const Tag = onClick ? 'button' : 'div';
  return (
    <Tag
      onClick={onClick}
      className={`flex items-center gap-2 px-2.5 py-1.5 rounded-[var(--radius-sm)] transition-colors ${
        onClick ? 'w-full text-left focus-ring hover:bg-[var(--bg-hover)]' : ''
      }`}
      style={{ border: '1px solid var(--border-color)' }}
    >
      {color && <span className="w-1.5 h-1.5 rounded-full shrink-0" style={{ backgroundColor: color }} />}
      {label && (
        <span className="text-[11px] flex-1 truncate" style={{ color: 'var(--text-primary)' }}>
          {label}
        </span>
      )}
      {children}
      {value !== undefined && (
        <span className="text-[11px] font-mono font-bold tabular-nums" style={{ color: color || 'var(--text-primary)' }}>
          {value}
        </span>
      )}
    </Tag>
  );
}

/**
 * LayerCardGrid — 卡片内的按钮网格
 */
export function LayerCardGrid({
  items,
}: {
  items: { key: string; label: string; desc?: string; onClick: () => void }[];
}) {
  return (
    <div className="grid grid-cols-2 gap-2">
      {items.map(item => (
        <button
          key={item.key}
          onClick={item.onClick}
          className="text-left px-2.5 py-2 rounded-[var(--radius-sm)] transition-colors hover:bg-[var(--bg-hover)] focus-ring"
          style={{ border: '1px solid var(--border-color)' }}
        >
          <div className="text-[11px] font-medium" style={{ color: 'var(--text-primary)' }}>
            {item.label}
          </div>
          {item.desc && (
            <div className="text-[9px] mt-0.5" style={{ color: 'var(--text-muted)' }}>
              {item.desc}
            </div>
          )}
        </button>
      ))}
    </div>
  );
}

/**
 * LayerCardAlert — 卡片内的告警横幅（高亮背景）
 */
export function LayerCardAlert({
  label, value, color, children,
}: {
  label: string;
  value: string | number;
  color: string;
  children?: React.ReactNode;
}) {
  return (
    <div
      className="flex items-center gap-2 px-3 py-1.5 rounded-[var(--radius-sm)]"
      style={{ backgroundColor: `color-mix(in srgb, ${color} 8%, transparent)` }}
    >
      <span className="text-[10px] font-bold" style={{ color }}>{label}</span>
      <span className="text-[11px] font-mono font-bold" style={{ color }}>{value}</span>
      {children}
    </div>
  );
}

/**
 * PipelineFlow — 管线流转视觉组件 (v3)
 *
 * 在跨层流转卡片中显示 data → judge → action 之间的流动状态。
 * v3 改进:
 * - 箭头使用下一层色，视觉上连贯
 * - 箭头加粗，使用层色渐变
 * - 当前层使用更醒目的边框和背景
 * - 非活跃层保持视觉连续
 */
export function PipelineFlow({
  steps,
}: {
  steps: {
    key: string;
    label: string;
    count: number;
    color: string;
    active?: boolean;
  }[];
}) {
  return (
    <div className="flex items-center gap-1">
      {steps.map((step, i) => {
        const isActive = step.active;
        const isLast = i === steps.length - 1;
        /* 箭头使用下一层色，让视觉流向更连贯 */
        const arrowColor = i < steps.length - 1 ? steps[i + 1].color : step.color;
        return (
          <React.Fragment key={step.key}>
            <div
              className="flex items-center gap-1.5 px-2.5 py-1.5 transition-all"
              style={{
                backgroundColor: isActive
                  ? `color-mix(in srgb, ${step.color} 10%, transparent)`
                  : 'color-mix(in srgb, var(--bg-hover) 40%, transparent)',
                border: isActive
                  ? `1px solid color-mix(in srgb, ${step.color} 30%, transparent)`
                  : '1px solid transparent',
                borderRadius: 'var(--radius-sm)',
                opacity: 1,
              }}
            >
              <span
                className="w-2 h-2 rounded-full shrink-0"
                style={{
                  backgroundColor: step.color,
                  boxShadow: isActive ? `0 0 0 2px color-mix(in srgb, ${step.color} 25%, transparent)` : 'none',
                }}
              />
              <span className="text-[11px] font-mono font-semibold" style={{ color: isActive ? step.color : 'var(--text-secondary)' }}>
                {step.label}
              </span>
              {step.count > 0 && (
                <span className="text-[11px] font-mono tabular-nums font-bold" style={{ color: step.color }}>
                  {step.count}
                </span>
              )}
            </div>
            {!isLast && (
              <svg width="20" height="20" viewBox="0 0 20 20" fill="none" aria-hidden="true" className="shrink-0 mx-1">
                <path
                  d="M7.5 5l5 5-5 5"
                  stroke={arrowColor}
                  strokeWidth="1.8"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  opacity="0.6"
                />
              </svg>
            )}
          </React.Fragment>
        );
      })}
    </div>
  );
}