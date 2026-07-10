import React, { useMemo, useCallback } from 'react';
import { useTodos } from '../hooks/useTodos';
import { TodoItem } from '../components/TodoItem';
import { AddTodoForm } from '../components/AddTodoForm';
import { TodoStatus, TodoUpdateRequest, TodoCreateRequest } from '../types';

interface TodosPageProps {
  onBack: () => void;
}

const STATUS_TABS: { value: TodoStatus | 'all'; label: string }[] = [
  { value: 'all', label: '全部' },
  { value: 'open', label: '未完成' },
  { value: 'done', label: '已完成' },
  { value: 'archived', label: '已归档' },
];

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

export function TodosPage({ onBack }: TodosPageProps) {
  const {
    items,
    total,
    count,
    filter,
    loading,
    error,
    setFilter,
    refresh,
    add,
    update,
    remove,
  } = useTodos();

  // 客户端 keyword 二次过滤 (后端已按 status/urgent/important 过滤)
  const visible = useMemo(() => {
    if (!filter.keyword) return items;
    const k = filter.keyword.toLowerCase();
    return items.filter(
      t => t.title.toLowerCase().includes(k) || (t.note || '').toLowerCase().includes(k)
    );
  }, [items, filter.keyword]);

  const handleToggleDone = useCallback(
    async (id: number) => {
      const target = items.find(it => it.id === id);
      if (!target) return;
      const next: TodoStatus = target.status === 'done' ? 'open' : 'done';
      try {
        await update(id, { status: next } as TodoUpdateRequest);
      } catch (e) {
        console.error('toggle done failed:', e);
      }
    },
    [items, update]
  );

  const handleDelete = useCallback(
    async (id: number) => {
      try {
        await remove(id);
      } catch (e) {
        console.error('delete todo failed:', e);
      }
    },
    [remove]
  );

  const handleImportantChange = useCallback(
    async (id: number, important: boolean) => {
      try {
        await update(id, { important } as TodoUpdateRequest);
      } catch (e) {
        console.error('important toggle failed:', e);
      }
    },
    [update]
  );

  const handleDeadlineChange = useCallback(
    async (id: number, deadline: string | null) => {
      try {
        await update(id, { deadline } as TodoUpdateRequest);
      } catch (e) {
        console.error('deadline change failed:', e);
      }
    },
    [update]
  );

  const handleAdd = useCallback(
    async (req: TodoCreateRequest) => {
      await add(req);
    },
    [add]
  );

  const handleUrgentToggle = (checked: boolean) => {
    setFilter({ urgent: checked ? true : null });
  };

  const handleImportantToggle = (checked: boolean) => {
    setFilter({ important: checked ? true : null });
  };

  const counts = count?.by_status ?? { open: 0, done: 0, archived: 0 };
  const priorityCounts = count?.by_priority ?? {
    urgent_important: 0,
    urgent_only: 0,
    important_only: 0,
    neither: 0,
  };

  return (
    <div className="todos-page">
      {/* 顶部标题区 */}
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-3">
          <button
            onClick={onBack}
            className="btn-ghost px-2.5 py-1.5 text-xs"
            title="返回首页"
            aria-label="返回首页"
          >
            <Icon>
              <line x1="19" y1="12" x2="5" y2="12" />
              <polyline points="12 19 5 12 12 5" />
            </Icon>
            返回首页
          </button>
          <h2 className="text-base font-bold" style={{ color: 'var(--text-primary)' }}>
            📝 待办 · 本周复盘
          </h2>
          <span className="text-xs" style={{ color: 'var(--text-muted)' }}>
            紧急由截止日期自动判断 (≤1 业务日, 过滤周末)
          </span>
        </div>
        <button
          onClick={refresh}
          disabled={loading}
          className="btn-ghost px-2.5 py-1.5 text-xs"
          title="刷新数据"
          aria-label="刷新"
        >
          {loading ? '刷新中…' : '刷新'}
        </button>
      </div>

      {/* 顶部错误条 */}
      {error && (
        <div
          className="rounded-[var(--radius-md)] p-2.5 mb-3 flex items-center justify-between text-xs"
          style={{
            backgroundColor: 'rgba(232, 93, 93, 0.12)',
            border: '1px solid #e85d5d',
            color: '#e85d5d',
          }}
        >
          <span>加载失败: {error}</span>
          <button onClick={refresh} className="btn-ghost px-2 py-0.5 text-xs" style={{ color: '#e85d5d', borderColor: '#e85d5d' }}>
            重试
          </button>
        </div>
      )}

      <div className="flex gap-4">
        {/* 左侧 sticky: 状态分布 */}
        <aside
          className="shrink-0"
          style={{
            width: 200,
            position: 'sticky',
            top: 16,
            alignSelf: 'flex-start',
            maxHeight: 'calc(100vh - 32px)',
            overflowY: 'auto',
          }}
        >
          <div
            className="rounded-[var(--radius-md)] p-3"
            style={{ backgroundColor: 'var(--bg-elevated)', border: '1px solid var(--border-color)' }}
          >
            <h3 className="text-xs font-bold mb-2.5" style={{ color: 'var(--text-muted)' }}>
              状态分布
            </h3>

            <ul className="space-y-1.5 text-xs">
              <li className="flex items-center justify-between">
                <span style={{ color: 'var(--text-secondary)' }}>未完成</span>
                <span className="font-mono tabular-nums" style={{ color: 'var(--text-primary)' }}>
                  {counts.open}
                </span>
              </li>
              <li className="flex items-center justify-between">
                <span style={{ color: 'var(--text-secondary)' }}>已完成</span>
                <span className="font-mono tabular-nums" style={{ color: 'var(--text-primary)' }}>
                  {counts.done}
                </span>
              </li>
              <li className="flex items-center justify-between">
                <span style={{ color: 'var(--text-secondary)' }}>已归档</span>
                <span className="font-mono tabular-nums" style={{ color: 'var(--text-muted)' }}>
                  {counts.archived}
                </span>
              </li>
            </ul>

            <div className="my-2.5 h-px" style={{ backgroundColor: 'var(--border-color)' }} />

            <h3 className="text-xs font-bold mb-2.5" style={{ color: 'var(--text-muted)' }}>
              四象限 <span className="text-[10px] font-normal">(紧急自动)</span>
            </h3>
            <ul className="space-y-1.5 text-xs">
              <li className="flex items-center justify-between">
                <span className="flex items-center gap-1.5">
                  <span
                    style={{
                      width: 8,
                      height: 8,
                      borderRadius: '50%',
                      backgroundColor: '#e85d5d',
                      display: 'inline-block',
                    }}
                  />
                  <span style={{ color: 'var(--text-secondary)' }}>紧急+重要</span>
                </span>
                <span className="font-mono tabular-nums" style={{ color: '#e85d5d' }}>
                  {priorityCounts.urgent_important}
                </span>
              </li>
              <li className="flex items-center justify-between">
                <span className="flex items-center gap-1.5">
                  <span
                    style={{
                      width: 8,
                      height: 8,
                      borderRadius: '50%',
                      backgroundColor: '#e8891a',
                      display: 'inline-block',
                    }}
                  />
                  <span style={{ color: 'var(--text-secondary)' }}>紧急+不重要</span>
                </span>
                <span className="font-mono tabular-nums" style={{ color: '#e8891a' }}>
                  {priorityCounts.urgent_only}
                </span>
              </li>
              <li className="flex items-center justify-between">
                <span className="flex items-center gap-1.5">
                  <span
                    style={{
                      width: 8,
                      height: 8,
                      borderRadius: '50%',
                      backgroundColor: '#3b82f6',
                      display: 'inline-block',
                    }}
                  />
                  <span style={{ color: 'var(--text-secondary)' }}>不紧急+重要</span>
                </span>
                <span className="font-mono tabular-nums" style={{ color: '#3b82f6' }}>
                  {priorityCounts.important_only}
                </span>
              </li>
              <li className="flex items-center justify-between">
                <span className="flex items-center gap-1.5">
                  <span
                    style={{
                      width: 8,
                      height: 8,
                      borderRadius: '50%',
                      border: '1.5px solid var(--text-muted)',
                      display: 'inline-block',
                    }}
                  />
                  <span style={{ color: 'var(--text-secondary)' }}>不紧急+不重要</span>
                </span>
                <span className="font-mono tabular-nums" style={{ color: 'var(--text-muted)' }}>
                  {priorityCounts.neither}
                </span>
              </li>
            </ul>

            <div className="my-2.5 h-px" style={{ backgroundColor: 'var(--border-color)' }} />

            <p
              className="text-[10px] text-center"
              style={{ color: 'var(--text-muted)' }}
              title="后端总数 (不受当前过滤影响)"
            >
              总计 {total} 条
            </p>
          </div>
        </aside>

        {/* 右侧主区: 筛选 + 列表 + 添加表单 */}
        <main className="flex-1 min-w-0">
          {/* 顶部筛选条 */}
          <div
            className="rounded-[var(--radius-md)] p-2.5 mb-3 flex items-center gap-2 flex-wrap"
            style={{ backgroundColor: 'var(--bg-elevated)', border: '1px solid var(--border-color)' }}
          >
            {/* status 4 段 tab */}
            {STATUS_TABS.map(t => {
              const active = filter.status === t.value;
              return (
                <button
                  key={t.value}
                  onClick={() => setFilter({ status: t.value })}
                  className="px-2.5 py-1 text-xs rounded-[var(--radius-sm)] transition-colors"
                  style={{
                    backgroundColor: active ? 'var(--bg-hover)' : 'transparent',
                    color: active ? 'var(--text-primary)' : 'var(--text-secondary)',
                    border: `1px solid ${active ? 'var(--text-muted)' : 'var(--border-color)'}`,
                  }}
                >
                  {t.label}
                </button>
              );
            })}

            <div
              className="w-px h-4 mx-1"
              style={{ backgroundColor: 'var(--border-color)' }}
              aria-hidden="true"
            />

            <label className="flex items-center gap-1 text-xs" style={{ color: 'var(--text-secondary)' }}>
              <input
                type="checkbox"
                checked={filter.urgent === true}
                onChange={e => handleUrgentToggle(e.target.checked)}
                className="focus-ring"
              />
              紧急
            </label>
            <label className="flex items-center gap-1 text-xs" style={{ color: 'var(--text-secondary)' }}>
              <input
                type="checkbox"
                checked={filter.important === true}
                onChange={e => handleImportantToggle(e.target.checked)}
                className="focus-ring"
              />
              重要
            </label>

            <input
              type="text"
              value={filter.keyword}
              onChange={e => setFilter({ keyword: e.target.value })}
              placeholder="关键词 (标题 / 备注)"
              className="ml-auto px-2 py-1 text-xs rounded-[var(--radius-sm)] focus-ring"
              style={{
                backgroundColor: 'var(--bg-card)',
                border: '1px solid var(--border-color)',
                color: 'var(--text-primary)',
                width: 220,
              }}
            />
          </div>

          {/* 列表 */}
          {loading && items.length === 0 ? (
            <p className="text-sm py-8 text-center" style={{ color: 'var(--text-muted)' }}>
              加载中…
            </p>
          ) : visible.length === 0 ? (
            <p className="text-sm py-8 text-center" style={{ color: 'var(--text-muted)' }}>
              {items.length === 0 ? '暂无待办' : '无匹配项'}
            </p>
          ) : (
            <div className="flex flex-col gap-2">
              {visible.map(item => (
                <TodoItem
                  key={item.id}
                  item={item}
                  onToggleDone={handleToggleDone}
                  onDelete={handleDelete}
                  onImportantToggle={handleImportantChange}
                  onDeadlineChange={handleDeadlineChange}
                />
              ))}
            </div>
          )}

          {/* 添加手动待办 */}
          <div className="mt-3">
            <AddTodoForm onAdd={handleAdd} />
          </div>
        </main>
      </div>
    </div>
  );
}
