/**
 * planningModel — 规划动作面板的纯类型 / 常量 / 计算 (B5 续拆: 从 KnowledgePlanningPanel 抽出)
 *
 * 只放无 React 依赖的内容; 展示区块见 PlanningActionCard.tsx。
 */
import { STAGE_COLORS, STAGE_LABELS } from './LifecycleProgress';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface PlanningAction {
  id: number;
  item_id: string;
  action_type: 'read' | 'review' | 'link' | 'refine' | 'publish';
  priority: number;
  title: string;
  description: string | null;
  current_stage: string | null;
  target_stage: string | null;
  status: string;
  created_at: string;
  completed_at: string | null;
  dismissed_at: string | null;
}

// ---------------------------------------------------------------------------
// Action type config
// ---------------------------------------------------------------------------

export const ACTION_CONFIG: Record<string, { color: string; label: string }> = {
  read:   { color: '#3b82f6', label: '阅读' },
  review: { color: '#8b5cf6', label: '评审' },
  link:   { color: '#22c55e', label: '关联' },
  refine: { color: '#f97316', label: '精炼' },
  publish:{ color: '#14b8a6', label: '发布' },
};

// ---------------------------------------------------------------------------
// Pure calculations
// ---------------------------------------------------------------------------

/** 优先级徽章配色 (>=8 红 / >=5 橙 / 其余灰) */
export function priorityBadgeStyle(priority: number) {
  return {
    backgroundColor: priority >= 8
      ? 'color-mix(in srgb, #ef4444 14%, transparent)'
      : priority >= 5
        ? 'color-mix(in srgb, #f59e0b 14%, transparent)'
        : 'color-mix(in srgb, #6b7280 14%, transparent)',
    color: priority >= 8
      ? '#ef4444'
      : priority >= 5
        ? '#f59e0b'
        : 'var(--text-muted)',
  };
}

/** 阶段标签 (无阶段 → '—') */
export function stageLabel(stage: string | null) {
  if (!stage) return '—';
  return STAGE_LABELS[stage] || stage;
}

/** 阶段配色 (无阶段 → 次要文字色) */
export function stageColor(stage: string | null) {
  if (!stage) return 'var(--text-muted)';
  return STAGE_COLORS[stage] || 'var(--text-muted)';
}
