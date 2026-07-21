import React, { useState, useEffect, useRef } from 'react';
import type { TaskItem } from '../types';

interface TaskMonitorProps {
  refreshKey?: number;
}

const STATUS_COLORS: Record<TaskItem['status'], string> = {
  pending: 'var(--color-warning)',
  processing: 'var(--color-info)',
  done: 'var(--color-success)',
  failed: 'var(--color-error)',
};

export function TaskMonitor({ refreshKey }: TaskMonitorProps) {
  const [tasks, setTasks] = useState<TaskItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [collapsed, setCollapsed] = useState(true);
  const [autoRefresh, setAutoRefresh] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const timerRef = useRef<number | null>(null);

  const loadTasks = () => {
    setLoading(true);
    setError(null);
    fetch('/api/knowledge/tasks?limit=20')
      .then(r => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        return r.json();
      })
      .then(data => {
        // 后端可能返回 { items: [...] } 或 [...] 两种格式
        const list: TaskItem[] = data.items || data.tasks || data || [];
        setTasks(Array.isArray(list) ? list : []);
        setLoading(false);
      })
      .catch(e => {
        setError(e?.message || String(e));
        setLoading(false);
      });
  };

  // 初始加载 + refreshKey 变化时刷新
  useEffect(() => {
    loadTasks();
  }, [refreshKey]);

  // 自动刷新 (10 秒)
  useEffect(() => {
    if (!autoRefresh) {
      if (timerRef.current) {
        window.clearInterval(timerRef.current);
        timerRef.current = null;
      }
      return;
    }
    timerRef.current = window.setInterval(loadTasks, 10000);
    return () => {
      if (timerRef.current) {
        window.clearInterval(timerRef.current);
        timerRef.current = null;
      }
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [autoRefresh]);

  return (
    <div
      className="rounded-[var(--radius-md)] mb-3"
      style={{ backgroundColor: 'var(--bg-elevated)', border: '1px solid var(--border-color)' }}
    >
      {/* 标题栏 (可点击折叠) */}
      <button
        onClick={() => setCollapsed(c => !c)}
        className="w-full flex items-center justify-between px-3 py-2 text-xs"
        style={{ color: 'var(--text-primary)', cursor: 'pointer' }}
      >
        <span className="flex items-center gap-2">
          <span style={{ display: 'inline-block', transform: collapsed ? 'rotate(-90deg)' : 'rotate(0)', transition: 'transform 0.15s' }}>▾</span>
          <span className="font-semibold">📋 任务监控</span>
          <span className="text-[10px]" style={{ color: 'var(--text-muted)' }}>
            ({tasks.length})
          </span>
        </span>
        <span className="flex items-center gap-2" onClick={e => e.stopPropagation()}>
          <button
            onClick={e => { e.stopPropagation(); setAutoRefresh(a => !a); }}
            className="btn-ghost px-2 py-0.5 text-[10px]"
            style={{ color: autoRefresh ? 'var(--color-ai)' : 'var(--text-muted)' }}
            title={autoRefresh ? '暂停自动刷新' : '恢复自动刷新'}
          >
            {autoRefresh ? '⏸ 自动' : '▶ 暂停'}
          </button>
          <button
            onClick={e => { e.stopPropagation(); loadTasks(); }}
            disabled={loading}
            className="btn-ghost px-2 py-0.5 text-[10px]"
            style={{ color: 'var(--text-muted)', opacity: loading ? 0.6 : 1 }}
            title="手动刷新"
          >
            {loading ? '…' : '↻ 刷新'}
          </button>
        </span>
      </button>

      {/* 展开时显示任务列表 */}
      {!collapsed && (
        <div className="px-3 pb-3">
          {error && (
            <div
              className="rounded-[var(--radius-sm)] p-2 mb-2 text-[11px]"
              style={{ backgroundColor: 'color-mix(in srgb, var(--color-error) 12%, transparent)', border: '1px solid var(--color-error)', color: 'var(--color-error)' }}
            >
              加载失败: {error}
            </div>
          )}
          {tasks.length === 0 ? (
            <p className="text-[11px] py-2 text-center" style={{ color: 'var(--text-muted)' }}>
              暂无任务
            </p>
          ) : (
            <div className="space-y-1">
              {tasks.map(t => (
                <div
                  key={t.id}
                  className="flex items-center gap-2 p-2 rounded-[var(--radius-sm)] text-[11px]"
                  style={{ backgroundColor: 'var(--bg-hover)' }}
                >
                  <span
                    className="shrink-0 px-1.5 py-0.5 rounded-[var(--radius-sm)] text-[10px] font-medium"
                    style={{
                      backgroundColor: STATUS_COLORS[t.status] || 'var(--text-muted)',
                      color: 'var(--text-on-light)',
                      opacity: 0.9,
                    }}
                  >
                    {t.status}
                  </span>
                  <span className="shrink-0" style={{ color: 'var(--text-primary)' }} title={t.task_type}>
                    {t.task_type}
                  </span>
                  <span className="flex-1 truncate text-[10px]" style={{ color: 'var(--text-muted)' }} title={`#${t.id}`}>
                    #{t.id}
                  </span>
                  <span className="shrink-0 text-[10px]" style={{ color: 'var(--text-muted)' }} title={`创建: ${t.created_at}\n更新: ${t.updated_at}`}>
                    {t.updated_at}
                  </span>
                  {t.error_message && (
                    <span className="shrink-0 text-[10px]" style={{ color: 'var(--color-error)' }} title={t.error_message}>
                      ⚠
                    </span>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
