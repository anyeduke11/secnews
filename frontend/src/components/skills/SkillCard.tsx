/**
 * SkillCard — 技能注册表单卡片 (v0.8 Phase A)
 *
 * 哨兵 V2 风格: hairline 边框 + bg-card + 类别色条 (左缘 3px), 徽章用等宽小字,
 * 状态 [ON]/[OFF] 由 SkillToggle 承载; React.memo 参考 AgihuntCard 先例
 * (20+ 卡片网格下避免无关重渲染)。
 * 快捷操作: [跑一次] 即时可用; [详情]/[历史] Phase A 跳转目标不存在 →
 * 视觉 disabled + title 提示 (B6 开放)。
 */
import React from 'react';
import { CATEGORY_LABELS, SKILL_TYPE_LABELS, SkillCategory, SkillSummary } from '../../types/skill';
import { Icon } from '../Icon';
import { SkillToggle } from './SkillToggle';

/** 类别色条 — 复用全局 category 色板 (sentinel 设计语言同源) */
const CATEGORY_COLOR: Record<SkillCategory, string> = {
  operations: 'var(--color-security)',
  compliance: 'var(--amber)',
  analysis: 'var(--color-ai)',
  report: 'var(--color-info)',
};

interface SkillCardProps {
  skill: SkillSummary;
  /** 二次确认通过后触发 (skill, 目标状态) */
  onToggle: (skill: SkillSummary, next: boolean) => void;
  onRun: (skill: SkillSummary) => void;
  /** Phase A 未接线: 不传则详情按钮渲染禁用态 */
  onDetail?: (skillId: string) => void;
  /** 启停请求在途 (开关禁用) */
  busy?: boolean;
  /** run 请求在途 (跑一次禁用) */
  running?: boolean;
}

export const SkillCard = React.memo(function SkillCard({
  skill,
  onToggle,
  onRun,
  onDetail,
  busy = false,
  running = false,
}: SkillCardProps) {
  const categoryColor = CATEGORY_COLOR[skill.category] ?? 'var(--line-strong)';

  return (
    <article
      data-testid={`skill-card-${skill.id}`}
      className="rounded-[var(--radius-md)] p-3 flex flex-col gap-2 h-full"
      style={{
        backgroundColor: 'var(--bg-card)',
        border: '1px solid var(--line)',
        borderLeft: `3px solid ${categoryColor}`,
      }}
    >
      {/* 顶部: 名称 + 启停开关 */}
      <div className="flex items-start justify-between gap-2">
        <h3
          className="text-sm font-bold truncate flex-1 min-w-0"
          style={{ color: 'var(--ink)' }}
          title={skill.name}
        >
          {skill.name}
        </h3>
        <SkillToggle
          enabled={skill.enabled}
          busy={busy}
          label={skill.name}
          onToggle={next => onToggle(skill, next)}
        />
      </div>

      {/* 描述: 两行截断 */}
      <p className="text-[12.5px] leading-relaxed line-clamp-2" style={{ color: 'var(--ink-2)' }} title={skill.desc}>
        {skill.desc}
      </p>

      {/* 徽章行: 类别 / 类型 / runner */}
      <div className="flex items-center gap-1.5 flex-wrap text-[11px] font-mono">
        <span
          className="px-1.5 py-0.5 rounded"
          style={{ color: categoryColor, backgroundColor: 'var(--bg-hover)' }}
        >
          {CATEGORY_LABELS[skill.category] ?? skill.category}
        </span>
        <span
          className="px-1.5 py-0.5 rounded border"
          style={{ color: 'var(--ink-2)', borderColor: 'var(--line-strong)' }}
        >
          {`${skill.skill_type}·${SKILL_TYPE_LABELS[skill.skill_type] ?? skill.skill_type}`}
        </span>
        <span className="truncate" style={{ color: 'var(--ink-3)' }} title={`runner: ${skill.runner} · timeout ${skill.timeout_seconds}s`}>
          {skill.runner}
        </span>
      </div>

      {/* 快捷操作 */}
      <div className="flex items-center gap-1.5 mt-auto pt-1">
        <button
          type="button"
          aria-label={`跑一次 ${skill.name}`}
          disabled={running}
          onClick={() => onRun(skill)}
          className="inline-flex items-center gap-1 h-7 px-2.5 rounded-md text-[12px] font-medium border transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
          style={{ borderColor: 'var(--mint)', color: 'var(--mint)' }}
        >
          <Icon size={12}>
            <polygon points="6 3 20 12 6 21 6 3" />
          </Icon>
          {running ? '提交中' : '跑一次'}
        </button>
        <button
          type="button"
          aria-label={`详情 ${skill.name}`}
          disabled={!onDetail}
          title={onDetail ? undefined : '详情页 B6 开放'}
          onClick={() => onDetail?.(skill.id)}
          className="inline-flex items-center gap-1 h-7 px-2.5 rounded-md text-[12px] border transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
          style={{ borderColor: 'var(--line-strong)', color: 'var(--ink-2)' }}
        >
          <Icon size={12}>
            <circle cx="12" cy="12" r="10" />
            <line x1="12" y1="16" x2="12" y2="12" />
            <line x1="12" y1="8" x2="12.01" y2="8" />
          </Icon>
          详情
        </button>
        <button
          type="button"
          aria-label={`历史 ${skill.name}`}
          disabled
          title="执行历史 B6 开放"
          className="inline-flex items-center gap-1 h-7 px-2.5 rounded-md text-[12px] border disabled:opacity-50 disabled:cursor-not-allowed"
          style={{ borderColor: 'var(--line-strong)', color: 'var(--ink-2)' }}
        >
          <Icon size={12}>
            <circle cx="12" cy="12" r="10" />
            <polyline points="12 6 12 12 16 14" />
          </Icon>
          历史
        </button>
      </div>
    </article>
  );
});
