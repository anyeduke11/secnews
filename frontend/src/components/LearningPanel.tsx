import React, { useState, useEffect, useCallback } from 'react';
import type { LearningPlan } from '../types';

export function LearningPanel() {
  const [plans, setPlans] = useState<LearningPlan[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [generating, setGenerating] = useState(false);
  const [taskState, setTaskState] = useState<Record<string, boolean>>({});

  const loadPlans = useCallback(() => {
    setLoading(true);
    setError(null);
    fetch('/api/knowledge/plans?status=active')
      .then(r => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        return r.json();
      })
      .then(data => {
        setPlans(data.plans || []);
        setLoading(false);
      })
      .catch(e => {
        setError(e?.message || String(e));
        setLoading(false);
      });
  }, []);

  useEffect(() => {
    loadPlans();
  }, [loadPlans]);

  const handleGenerate = () => {
    setGenerating(true);
    fetch('/api/knowledge/plans/generate', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ domains: [] }),
    })
      .then(r => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        return r.json();
      })
      .then(() => {
        setTimeout(loadPlans, 500);
      })
      .catch(e => setError(e?.message || String(e)))
      .finally(() => setGenerating(false));
  };

  const toggleTask = (key: string) => {
    setTaskState(prev => ({ ...prev, [key]: !prev[key] }));
  };

  if (loading) {
    return <p className="text-xs" style={{ color: 'var(--text-muted)' }}>加载中…</p>;
  }

  if (error) {
    return (
      <p className="text-xs" style={{ color: '#e85d5d' }}>
        加载失败: {error}
      </p>
    );
  }

  if (plans.length === 0) {
    return (
      <div>
        <p className="text-xs mb-3" style={{ color: 'var(--text-muted)' }}>
          暂无学习计划。点击生成按钮创建。
        </p>
        <button
          onClick={handleGenerate}
          disabled={generating}
          className="btn-ghost px-3 py-1.5 text-xs"
          style={{ color: 'var(--color-ai)', opacity: generating ? 0.6 : 1 }}
        >
          {generating ? '生成中…' : '生成学习计划'}
        </button>
      </div>
    );
  }

  const plan = plans[0];

  return (
    <div>
      <div className="flex items-center justify-between mb-2">
        <span className="text-[10px]" style={{ color: 'var(--text-muted)' }}>
          本周计划: {plan.week}
        </span>
        <button
          onClick={handleGenerate}
          disabled={generating}
          className="btn-ghost px-2 py-0.5 text-[10px]"
          style={{ color: 'var(--color-ai)', opacity: generating ? 0.6 : 1 }}
        >
          {generating ? '生成中…' : '重新生成'}
        </button>
      </div>

      {plan.plan_data.goals && plan.plan_data.goals.length > 0 && (
        <div className="mb-3">
          <p className="text-[10px] mb-1" style={{ color: 'var(--text-muted)' }}>学习目标</p>
          <ul className="text-xs space-y-1" style={{ color: 'var(--text-primary)' }}>
            {plan.plan_data.goals.map((g, i) => (
              <li key={i} className="flex gap-1.5">
                <span style={{ color: 'var(--color-ai)' }}>•</span>
                <span>{g}</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      <div>
        <p className="text-[10px] mb-1" style={{ color: 'var(--text-muted)' }}>
          任务清单 ({plan.plan_data.tasks?.length || 0})
        </p>
        {plan.plan_data.tasks && plan.plan_data.tasks.length > 0 ? (
          <div className="space-y-1">
            {plan.plan_data.tasks.map((t, i) => {
              const key = `${plan.id}-${i}`;
              const done = taskState[key] ?? t.completed;
              return (
                <label
                  key={i}
                  className="flex items-start gap-2 text-xs cursor-pointer p-1 rounded-[var(--radius-sm)]"
                  style={{ color: 'var(--text-primary)' }}
                >
                  <input
                    type="checkbox"
                    checked={done}
                    onChange={() => toggleTask(key)}
                    style={{ marginTop: '2px', accentColor: 'var(--color-ai)' }}
                  />
                  <span style={{ textDecoration: done ? 'line-through' : 'none', opacity: done ? 0.6 : 1 }}>
                    {t.title}
                  </span>
                </label>
              );
            })}
          </div>
        ) : (
          <p className="text-[10px]" style={{ color: 'var(--text-muted)' }}>暂无任务</p>
        )}
      </div>
    </div>
  );
}
