/**
 * KnowledgePlanningPanel — 个性化规划动作面板 (Phase 13)
 *
 * 展示系统根据知识条目生命周期阶段自动生成的待办规划动作，
 * 支持标记完成和忽略操作。
 */
import { useState, useEffect, useCallback } from 'react';
import { Icon } from '../Icon';
import { listPlanningActions, updatePlanningActionStatus } from '../../api/action';
import { useAbortGuard } from '../../hooks/useAbortGuard';
import { PlanningActionCard } from './PlanningActionCard';
import type { PlanningAction } from './planningModel';

export function KnowledgePlanningPanel() {
  const [actions, setActions] = useState<PlanningAction[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [updatingIds, setUpdatingIds] = useState<Set<number>>(new Set());
  const dead = useAbortGuard(); // P1-7 竞态守卫: 卸载后不写状态

  // ── Fetch ──────────────────────────────────────────────────────────────────
  const fetchActions = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await listPlanningActions<PlanningAction>('pending');
      if (dead.current) return;
      // API 已按 priority DESC 排序，但本地再确保一次
      data.sort((a, b) => b.priority - a.priority);
      setActions(data);
    } catch (e) {
      if (dead.current) return;
      setError(e instanceof Error ? e.message : '加载规划动作失败');
    } finally {
      if (!dead.current) setLoading(false);
    }
  }, [dead]);

  useEffect(() => {
    fetchActions();
  }, [fetchActions]);

  // ── Status update ──────────────────────────────────────────────────────────
  const updateStatus = useCallback(async (id: number, status: string) => {
    setUpdatingIds(prev => new Set(prev).add(id));
    try {
      await updatePlanningActionStatus(id, status);
      if (dead.current) return;
      // 从列表中移除
      setActions(prev => prev.filter(a => a.id !== id));
    } catch (e) {
      console.error('状态更新失败:', e);
    } finally {
      if (!dead.current) {
        setUpdatingIds(prev => {
          const next = new Set(prev);
          next.delete(id);
          return next;
        });
      }
    }
  }, [dead]);

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
        {actions.map(action => (
          <PlanningActionCard
            key={action.id}
            action={action}
            isUpdating={updatingIds.has(action.id)}
            onUpdateStatus={updateStatus}
          />
        ))}
      </div>
    </div>
  );
}
