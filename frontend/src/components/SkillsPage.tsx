import React, { useState } from 'react';
import { useSkills } from '../hooks/useSkills';
import { SkillCard } from '../components/SkillCard';
import { AddSkillForm } from '../components/AddSkillForm';
import { SkillItem, SkillSource, SkillUpdateRequest } from '../types';

interface SkillsPageProps {
  onBack: () => void;
}

const SOURCE_TABS: { value: SkillSource | 'all'; label: string }[] = [
  { value: 'all', label: '全部' },
  { value: 'npx', label: 'npx' },
  { value: 'uvx', label: 'uvx' },
  { value: 'curl', label: 'curl' },
  { value: 'git', label: 'git' },
  { value: 'manual', label: 'manual' },
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

export function SkillsPage({ onBack }: SkillsPageProps) {
  const {
    items, total, countsBySource, loading, error,
    source, tag, keyword,
    setSource, setTag, setKeyword,
    add, update, remove,
  } = useSkills();
  const [editing, setEditing] = useState<SkillItem | null>(null);
  const [showForm, setShowForm] = useState(false);

  const handleSubmit = async (req: any) => {
    if (editing) {
      await update(editing.id, req as SkillUpdateRequest);
      setEditing(null);
      setShowForm(false);
    } else {
      await add(req);
    }
  };

  const handleEdit = (item: SkillItem) => {
    setEditing(item);
    setShowForm(true);
  };

  const handleDelete = async (id: number) => {
    try {
      await remove(id);
    } catch (e: any) {
      window.alert(`删除失败: ${e?.message || e}`);
    }
  };

  // 提取所有 tags 用于 filter chips
  const allTags = Array.from(
    new Set(items.flatMap(it => it.tags || []))
  ).sort();

  return (
    <div className="skills-page">
      {/* 顶部标题区 */}
      <div className="flex items-center justify-between mb-4 flex-wrap gap-2">
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
            🧩 Skill 管理
          </h2>
          <span className="text-xs" style={{ color: 'var(--text-muted)' }}>
            一键复制安装指令到 Agent
          </span>
        </div>
        <div className="flex items-center gap-2">
          <span className="text-xs" style={{ color: 'var(--text-muted)' }}>
            共 {total} 条
          </span>
          <button
            onClick={() => {
              setEditing(null);
              setShowForm(s => !s);
            }}
            className="btn-ghost px-3 py-1.5 text-xs"
            style={{
              backgroundColor: showForm && !editing ? 'var(--bg-hover)' : undefined,
              color: 'var(--color-ai)',
              borderColor: 'var(--color-ai)',
            }}
          >
            {showForm && !editing ? '收起表单' : '+ 新增'}
          </button>
        </div>
      </div>

      {/* 错误条 */}
      {error && (
        <div
          className="rounded-[var(--radius-md)] p-2.5 mb-3 text-xs"
          style={{
            backgroundColor: 'rgba(232, 93, 93, 0.12)',
            border: '1px solid #e85d5d',
            color: '#e85d5d',
          }}
        >
          加载失败: {error}
        </div>
      )}

      {/* 新增 / 编辑表单 */}
      {showForm && (
        <div className="mb-3">
          <AddSkillForm
            editing={editing}
            onSubmit={handleSubmit}
            onCancel={editing ? () => { setEditing(null); setShowForm(false); } : undefined}
          />
        </div>
      )}

      {/* 筛选条: source tabs + tag chips + keyword 输入 */}
      <div
        className="rounded-[var(--radius-md)] p-2.5 mb-3 flex items-center gap-2 flex-wrap"
        style={{ backgroundColor: 'var(--bg-elevated)', border: '1px solid var(--border-color)' }}
      >
        {SOURCE_TABS.map(t => {
          const active = source === t.value;
          const cnt = countsBySource[t.value] ?? 0;
          return (
            <button
              key={t.value}
              onClick={() => setSource(t.value)}
              className="px-2.5 py-1 text-xs rounded-[var(--radius-sm)] transition-colors"
              style={{
                backgroundColor: active ? 'var(--bg-hover)' : 'transparent',
                color: active ? 'var(--text-primary)' : 'var(--text-secondary)',
                border: `1px solid ${active ? 'var(--text-muted)' : 'var(--border-color)'}`,
              }}
            >
              {t.label}
              <span
                className="ml-1 font-mono tabular-nums text-[10px]"
                style={{ color: active ? 'var(--color-ai)' : 'var(--text-muted)' }}
              >
                {cnt}
              </span>
            </button>
          );
        })}

        <div className="w-px h-4 mx-1" style={{ backgroundColor: 'var(--border-color)' }} aria-hidden="true" />

        {/* tag chips (从当前结果里提取; 切换 source 时刷新) */}
        {allTags.length > 0 && (
          <>
            {allTags.slice(0, 8).map(tg => {
              const active = tag === tg;
              return (
                <button
                  key={tg}
                  onClick={() => setTag(active ? null : tg)}
                  className="px-2 py-0.5 text-[10px] font-mono rounded-[var(--radius-sm)]"
                  style={{
                    backgroundColor: active ? 'var(--color-ai)' : 'var(--bg-hover)',
                    color: active ? '#0a0d12' : 'var(--text-muted)',
                    border: '1px solid var(--border-color)',
                  }}
                >
                  #{tg}
                </button>
              );
            })}
            <div className="w-px h-4 mx-1" style={{ backgroundColor: 'var(--border-color)' }} aria-hidden="true" />
          </>
        )}

        <input
          type="text"
          value={keyword}
          onChange={e => setKeyword(e.target.value)}
          placeholder="搜索 名称 / 简介"
          className="ml-auto px-2 py-1 text-xs rounded-[var(--radius-sm)] focus-ring"
          style={{
            backgroundColor: 'var(--bg-card)',
            border: '1px solid var(--border-color)',
            color: 'var(--text-primary)',
            width: 200,
          }}
        />
      </div>

      {/* 列表 */}
      {loading && items.length === 0 ? (
        <p className="text-sm py-8 text-center" style={{ color: 'var(--text-muted)' }}>
          加载中…
        </p>
      ) : items.length === 0 ? (
        <p className="text-sm py-8 text-center" style={{ color: 'var(--text-muted)' }}>
          {total === 0 ? '暂无 Skill, 点击「+ 新增」开始管理' : '无匹配项'}
        </p>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
          {items.map(item => (
            <SkillCard
              key={item.id}
              item={item}
              onEdit={handleEdit}
              onDelete={handleDelete}
            />
          ))}
        </div>
      )}
    </div>
  );
}
