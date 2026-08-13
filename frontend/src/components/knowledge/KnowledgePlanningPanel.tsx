/**
 * KnowledgePlanningPanel — 个性化规划动作面板 (Phase 13)
 *
 * 展示系统根据知识条目生命周期阶段自动生成的待办规划动作，
 * 支持标记完成和忽略操作。
 */
import React, { useState, useEffect, useCallback } from 'react';
import { Icon } from '../Icon';
import { STAGE_COLORS, STAGE_LABELS } from './LifecycleProgress';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface PlanningAction {
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

const ACTION_CONFIG: Record<string, { color: string; label: string }> = {
  read:   { color: '#3b82f6', label: '阅读' },
  review: { color: '#8b5cf6', label: '评审' },
  link:   { color: '#22c55e', label: '关联' },
  refine: { color: '#f97316', label: '精炼' },
  publish:{ color: '#14b8a6', label: '发布' },
};

// ---------------------------------------------------------------------------
// Action type icons (Lucide-style)
// ---------------------------------------------------------------------------

function ActionTypeIcon({ type }: { type: string }) {
  const cfg = ACTION_CONFIG[type] || { color: 'var(--text-muted)', label: type };
  switch (type) {
    case 'read':
      return (
        <Icon size={13}>
          <path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20" />
          <path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z" />
        </Icon>
      );
    case 'review':
      return (
        <Icon size={13}>
          <circle cx="12" cy="12" r="3" />
          <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z" />
        </Icon>
      );
    case 'link':
      return (
        <Icon size={13}>
          <path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71" />
          <path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71" />
        </Icon>
      );
    case 'refine':
      return (
        <Icon size={13}>
          <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7" />
          <path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z" />
        </Icon>
      );
    case 'publish':
      return (
        <Icon size={13}>
          <line x1="12" y1="19" x2="12" y2="5" />
          <polyline points="5 12 12 5 19 12" />
        </Icon>
      );
    default:
      return (
        <Icon size={13}>
          <circle cx="12" cy="12" r="10" />
          <line x1="12" y1="16" x2="12" y2="12" />
          <line x1="12" y1="8" x2="12.01" y2="8" />
        </Icon>
      );
  }
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export function KnowledgePlanningPanel() {
  const [actions, setActions] = useState<PlanningAction[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [updatingIds, setUpdatingIds] = useState<Set<number>>(new Set());

  // ── Fetch ──────────────────────────────────────────────────────────────────
  const fetchActions = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch('/api/kl/planning-actions?status=pending');
      if (!res.ok) {
        throw new Error(`请求失败: ${res.status} ${res.statusText}`);
      }
      const data: PlanningAction[] = await res.json();
      // API 已按 priority DESC 排序，但本地再确保一次
      data.sort((a, b) => b.priority - a.priority);
      setActions(data);
    } catch (e) {
      setError(e instanceof Error ? e.message : '加载规划动作失败');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchActions();
  }, [fetchActions]);

  // ── Status update ──────────────────────────────────────────────────────────
  const updateStatus = useCallback(async (id: number, status: string) => {
    setUpdatingIds(prev => new Set(prev).add(id));
    try {
      const res = await fetch(`/api/kl/planning-actions/${id}/status`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ status }),
      });
      if (!res.ok) {
        const detail = await res.json().catch(() => ({}));
        console.error('状态更新失败:', detail);
        return;
      }
      // 从列表中移除
      setActions(prev => prev.filter(a => a.id !== id));
    } catch (e) {
      console.error('状态更新请求异常:', e);
    } finally {
      setUpdatingIds(prev => {
        const next = new Set(prev);
        next.delete(id);
        return next;
      });
    }
  }, []);

  // ── Render helpers ─────────────────────────────────────────────────────────
  const renderStageLabel = (stage: string | null) => {
    if (!stage) return '—';
    return STAGE_LABELS[stage] || stage;
  };

  const renderStageColor = (stage: string | null) => {
    if (!stage) return 'var(--text-muted)';
    return STAGE_COLORS[stage] || 'var(--text-muted)';
  };

  // ── Loading state ──────────────────────────────────────────────────────────
  if (loading) {
    return (
      <div
        className="rounded-[var(--radius-md)] p-3.5"
        style={{ backgroundColor: 'var(--bg-elevated)', border: '1px solid var(--border-color)' }}
      >
        <div className="flex items-center justify-center py-6">
          <div
            className="w-5 h-5 rounded-full border-2 animate-spin"
            style={{
              borderColor: 'var(--border-color)',
              borderTopColor: 'var(--text-muted)',
            }}
          />
          <span className="ml-2 text-xs" style={{ color: 'var(--text-muted)' }}>
            加载规划动作...
          </span>
        </div>
      </div>
    );
  }

  // ── Error state ────────────────────────────────────────────────────────────
  if (error) {
    return (
      <div
        className="rounded-[var(--radius-md)] p-3.5"
        style={{ backgroundColor: 'var(--bg-elevated)', border: '1px solid var(--border-color)' }}
      >
        <div className="flex items-center gap-2 py-3">
          <Icon size={14}>
            <circle cx="12" cy="12" r="10" />
            <line x1="12" y1="8" x2="12" y2="12" />
            <line x1="12" y1="16" x2="12.01" y2="16" />
          </Icon>
          <span className="text-xs" style={{ color: 'var(--text-secondary)' }}>
            {error}
          </span>
          <button
            className="ml-auto text-xs underline hover:no-underline"
            style={{ color: 'var(--text-muted)' }}
            onClick={fetchActions}
          >
            重试
          </button>
        </div>
      </div>
    );
  }

  // ── Empty state ────────────────────────────────────────────────────────────
  if (actions.length === 0) {
    return (
      <div
        className="rounded-[var(--radius-md)] p-3.5"
        style={{ backgroundColor: 'var(--bg-elevated)', border: '1px solid var(--border-color)' }}
      >
        <div className="flex flex-col items-center justify-center py-8 gap-2">
          <Icon size={20}>
            <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
            <polyline points="14 2 14 8 20 8" />
            <line x1="16" y1="13" x2="8" y2="13" />
            <line x1="16" y1="17" x2="8" y2="17" />
          </Icon>
          <span className="text-xs" style={{ color: 'var(--text-muted)' }}>
            暂无待办规划动作，系统将在下次检查时自动生成
          </span>
        </div>
      </div>
    );
  }

  // ── List ───────────────────────────────────────────────────────────────────
  return (
    <div
      className="rounded-[var(--radius-md)] p-3.5"
      style={{ backgroundColor: 'var(--bg-elevated)', border: '1px solid var(--border-color)' }}
    >
      <div className="flex items-center gap-2 mb-2">
        <h3
          className="text-sm font-semibold"
          style={{ color: 'var(--text-primary)' }}
        >
          规划动作
        </h3>
        <span
          className="text-[10px] px-1.5 py-0.5 rounded-full"
          style={{
            backgroundColor: 'color-mix(in srgb, var(--area-accent) 12%, transparent)',
            color: 'var(--text-secondary)',
          }}
        >
          {actions.length} 项待办
        </span>
      </div>

      <div className="space-y-2">
        {actions.map(action => {
          const cfg = ACTION_CONFIG[action.action_type] || { color: 'var(--text-muted)', label: action.action_type };
          const isUpdating = updatingIds.has(action.id);

          return (
            <div
              key={action.id}
              className="rounded-md p-2.5 transition-colors duration-150"
              style={{
                backgroundColor: 'color-mix(in srgb, var(--bg-base) 50%, transparent)',
                border: '1px solid var(--border-color)',
                opacity: isUpdating ? 0.5 : 1,
              }}
            >
              <div className="flex items-start gap-2.5">
                {/* 动作类型徽章 */}
                <div
                  className="w-7 h-7 rounded-md flex items-center justify-center shrink-0 mt-0.5"
                  style={{
                    backgroundColor: `color-mix(in srgb, ${cfg.color} 14%, transparent)`,
                    color: cfg.color,
                  }}
                >
                  <ActionTypeIcon type={action.action_type} />
                </div>

                {/* 内容区 */}
                <div className="flex-1 min-w-0">
                  {/* 标题行 */}
                  <div className="flex items-center gap-1.5 flex-wrap">
                    <span
                      className="text-xs font-medium"
                      style={{ color: 'var(--text-primary)' }}
                    >
                      {action.title}
                    </span>
                    {/* 优先级徽章 */}
                    <span
                      className="text-[10px] font-semibold px-1 rounded"
                      style={{
                        backgroundColor: action.priority >= 8
                          ? 'color-mix(in srgb, #ef4444 14%, transparent)'
                          : action.priority >= 5
                            ? 'color-mix(in srgb, #f59e0b 14%, transparent)'
                            : 'color-mix(in srgb, #6b7280 14%, transparent)',
                        color: action.priority >= 8
                          ? '#ef4444'
                          : action.priority >= 5
                            ? '#f59e0b'
                            : 'var(--text-muted)',
                      }}
                    >
                      P{action.priority}
                    </span>
                  </div>

                  {/* 描述 */}
                  {action.description && (
                    <p
                      className="text-[11px] mt-0.5 leading-relaxed"
                      style={{ color: 'var(--text-secondary)' }}
                    >
                      {action.description}
                    </p>
                  )}

                  {/* 阶段流转 */}
                  {(action.current_stage || action.target_stage) && (
                    <div className="flex items-center gap-1 mt-1.5">
                      {action.current_stage && (
                        <span
                          className="text-[10px] px-1.5 py-0.5 rounded"
                          style={{
                            backgroundColor: `color-mix(in srgb, ${renderStageColor(action.current_stage)} 12%, transparent)`,
                            color: renderStageColor(action.current_stage),
                          }}
                        >
                          {renderStageLabel(action.current_stage)}
                        </span>
                      )}
                      <span style={{ color: 'var(--text-muted)', fontSize: 10 }}>→</span>
                      {action.target_stage && (
                        <span
                          className="text-[10px] px-1.5 py-0.5 rounded font-medium"
                          style={{
                            backgroundColor: `color-mix(in srgb, ${renderStageColor(action.target_stage)} 14%, transparent)`,
                            color: renderStageColor(action.target_stage),
                          }}
                        >
                          {renderStageLabel(action.target_stage)}
                        </span>
                      )}
                    </div>
                  )}
                </div>

                {/* 操作按钮 */}
                <div className="flex items-center gap-1 shrink-0">
                  <button
                    className="text-[11px] px-2 py-1 rounded transition-colors duration-100"
                    style={{
                      backgroundColor: 'color-mix(in srgb, var(--area-accent) 10%, transparent)',
                      color: 'var(--area-accent)',
                    }}
                    disabled={isUpdating}
                    onClick={() => updateStatus(action.id, 'completed')}
                    title="标记完成"
                  >
                    标记完成
                  </button>
                  <button
                    className="text-[11px] px-2 py-1 rounded transition-colors duration-100"
                    style={{
                      color: 'var(--text-muted)',
                    }}
                    disabled={isUpdating}
                    onClick={() => updateStatus(action.id, 'dismissed')}
                    title="忽略"
                  >
                    忽略
                  </button>
                </div>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}