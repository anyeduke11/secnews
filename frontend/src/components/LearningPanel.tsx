/**
 * LearningPanel — 学习计划面板（周计划 + 任务勾选 + 重新生成）。
 *
 * Phase 3: 错误态用 --color-error, 空态/加载态/任务样式 token 化。
 */
import React, { useState, useEffect, useCallback, useRef } from 'react';
import type { LearningPlan } from '../types';
import { EmptyState } from './EmptyState';

export function LearningPanel() {
  const [plans, setPlans] = useState<LearningPlan[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [generating, setGenerating] = useState(false);
  const [genProgress, setGenProgress] = useState('');
  const [genElapsed, setGenElapsed] = useState(0);
  const genTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const genPollRef = useRef<ReturnType<typeof setInterval> | null>(null);
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

  const stopGen = () => {
    if (genTimerRef.current) { clearInterval(genTimerRef.current); genTimerRef.current = null; }
    if (genPollRef.current) { clearInterval(genPollRef.current); genPollRef.current = null; }
  };

  const handleGenerate = () => {
    setGenerating(true);
    setGenProgress('创建任务...');
    setGenElapsed(0);
    const startTime = Date.now();

    // 计时器
    genTimerRef.current = setInterval(() => {
      setGenElapsed(Math.round((Date.now() - startTime) / 1000));
    }, 1000);

    fetch('/api/knowledge/plans/generate', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ domains: [] }),
    })
      .then(r => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        return r.json();
      })
      .then(data => {
        const taskId = data?.task_id ?? data?.task?.id;
        if (!taskId) {
          stopGen();
          // No task_id but status=done means plan was generated directly
          if (data?.status === 'done') {
            setGenerating(false);
            setGenProgress('');
            loadPlans();
            return;
          }
          setError('未返回 task_id');
          setGenerating(false);
          return;
        }

        // If status is already done, plan was generated directly
        if (data?.status === 'done') {
          stopGen();
          setGenerating(false);
          setGenProgress('');
          loadPlans();
          return;
        }

        setGenProgress('等待 Agent 处理...');

        // 轮询任务状态，每 2s 一次，最多 60s
        let polls = 0;
        genPollRef.current = setInterval(() => {
          polls++;
          fetch(`/api/knowledge/tasks/${taskId}`)
            .then(r => r.json())
            .then(task => {
              const status = task?.status;
              if (status === 'done') {
                stopGen();
                setGenerating(false);
                setGenProgress('');
                loadPlans();
              } else if (status === 'failed') {
                stopGen();
                setError(task?.error_message || '任务执行失败');
                setGenerating(false);
              } else if (polls >= 30) {
                // 30 次轮询(~60s)仍未完成，提示 Agent 可能未运行
                stopGen();
                setError('任务已创建但超时未完成，请确认 Agent 是否在运行');
                setGenerating(false);
              } else if (status === 'processing') {
                setGenProgress('Agent 正在生成...');
              } else {
                setGenProgress('等待 Agent 处理...');
              }
            })
            .catch(() => { /* ignore poll errors */ });
        }, 2000);
      })
      .catch(e => {
        stopGen();
        setError(e?.message || String(e));
        setGenerating(false);
      });
  };

  const toggleTask = (key: string) => {
    setTaskState(prev => ({ ...prev, [key]: !prev[key] }));
  };

  if (loading) {
    return (
      <p className="text-xs" style={{ color: 'var(--text-muted)' }}>
        加载中…
      </p>
    );
  }

  if (error) {
    return (
      <EmptyState
        compact
        title={`加载失败: ${error}`}
        description="点击重新生成可重试"
        actionLabel="重新生成"
        onAction={handleGenerate}
      />
    );
  }

  if (plans.length === 0) {
    return (
      <div>
        <EmptyState
          title={generating ? genProgress : '暂无学习计划'}
          description={generating
            ? `${genElapsed}s — 等待 AI Agent 执行 knowledge-master skill`
            : '点击生成按钮创建'}
          actionLabel={generating ? '生成中…' : '生成学习计划'}
          onAction={generating ? undefined : handleGenerate}
        />
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
          <p className="text-[10px] mb-1" style={{ color: 'var(--text-muted)' }}>
            学习目标
          </p>
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
          <p className="text-[10px]" style={{ color: 'var(--text-muted)' }}>
            暂无任务
          </p>
        )}
      </div>
    </div>
  );
}
