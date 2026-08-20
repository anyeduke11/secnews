/**
 * OutboxMode — 整理模式 (Phase 17)
 *
 * 知识条目待处理列表，按 attention_score 降序排列。
 * 支持批量操作（标记已读 / 归档 / 生成摘要）和多维筛选。
 *
 * 路由: /knowledge/outbox
 */
import React, { useState, useEffect, useCallback } from 'react';
import { Icon } from '../Icon';
import { EmptyState } from '../EmptyState';
import { STAGE_LABELS, STAGE_COLORS, ALL_STAGES } from './LifecycleProgress';
import type { KnowledgeItem } from '../../types';
import { OnboardingHint } from '../layout/OnboardingHint';

// ── 扩展类型: 后端可能返回的额外字段 ──────────────────

interface OutboxKnowledgeItem extends KnowledgeItem {
  lifecycle?: string;
  attention_score?: number;
  summary?: string;
}

// ── 常量 ──────────────────────────────────────────────────────

const LIFECYCLE_OPTIONS = [
  { value: '', label: '全部阶段' },
  { value: 'kl:raw', label: '原始' },
  { value: 'kl:refine', label: '精炼' },
  { value: 'kl:link', label: '关联' },
  { value: 'kl:structure', label: '结构化' },
  { value: 'kl:publish', label: '发布' },
];

const DATE_RANGE_OPTIONS = [
  { value: 'D7', label: '最近 7 天' },
  { value: 'D30', label: '最近 30 天' },
  { value: 'ALL', label: '全部时间' },
] as const;

const SCORE_RANGE_OPTIONS = [
  { value: '', label: '全部分数' },
  { value: '0-20', label: '0-20' },
  { value: '21-40', label: '21-40' },
  { value: '41-60', label: '41-60' },
  { value: '61-80', label: '61-80' },
  { value: '81-100', label: '81-100' },
];

function getAttentionColor(score: number): string {
  if (score <= 20) return 'var(--text-muted)';
  if (score <= 40) return 'var(--color-info)';
  if (score <= 60) return 'var(--color-success)';
  if (score <= 80) return 'var(--color-warning)';
  return 'var(--color-error)';
}

function getLifecycleColor(stage: string): string {
  return STAGE_COLORS[stage] || 'var(--text-muted)';
}

function getLifecycleLabel(stage: string): string {
  return STAGE_LABELS[stage] || stage;
}

function dateRangeToSince(range: string): string | null {
  if (range === 'ALL') return null;
  const now = Date.now();
  const ms: Record<string, number> = {
    D7: 7 * 24 * 60 * 60 * 1000,
    D30: 30 * 24 * 60 * 60 * 1000,
  };
  const offset = ms[range];
  if (!offset) return null;
  return new Date(now - offset).toISOString();
}

function matchesScoreRange(score: number | undefined | null, range: string): boolean {
  if (!range) return true;
  const [lo, hi] = range.split('-').map(Number);
  const s = score ?? 0;
  return s >= lo && s <= hi;
}

// ── 主组件 ────────────────────────────────────────────────────

export function OutboxMode() {
  // 筛选状态
  const [lifecycleFilter, setLifecycleFilter] = useState('');
  const [dateRange, setDateRange] = useState<string>('D7');
  const [scoreRange, setScoreRange] = useState('');

  // 数据状态
  const [items, setItems] = useState<OutboxKnowledgeItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [attentionAvailable, setAttentionAvailable] = useState(false);

  // 选中状态
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());

  // 已读状态 (客户端本地跟踪)
  const [readIds, setReadIds] = useState<Set<string>>(new Set());

  // 批量操作反馈
  const [batchBusy, setBatchBusy] = useState(false);

  // ── 数据加载 ──

  const fetchItems = useCallback(() => {
    setLoading(true);
    setError(null);

    const params = new URLSearchParams();
    params.set('limit', '50');
    const since = dateRangeToSince(dateRange);
    if (since) params.set('since', since);
    // 尝试传递 sort/lifecycle 参数（后端可能暂不支持，静默忽略）
    params.set('sort', 'attention_score');
    params.set('order', 'desc');
    if (lifecycleFilter) params.set('lifecycle', lifecycleFilter);

    fetch(`/api/knowledge/items?${params.toString()}`)
      .then(async r => {
        if (!r.ok) throw new Error(`请求失败 (${r.status})`);
        return r.json();
      })
      .then(data => {
        const rawItems: OutboxKnowledgeItem[] = data.items || [];
        setItems(rawItems);
        // 检查是否有 attention_score 数据
        const hasAttention = rawItems.some(
          item => item.attention_score !== undefined && item.attention_score !== null && item.attention_score > 0
        );
        setAttentionAvailable(hasAttention);
      })
      .catch(e => {
        setError(e?.message || '加载失败');
        setItems([]);
      })
      .finally(() => {
        setLoading(false);
      });
  }, [lifecycleFilter, dateRange]);

  useEffect(() => {
    fetchItems();
  }, [fetchItems]);

  // ── 客户端筛选 ──

  const filteredItems = items.filter(item => {
    // 生命周期筛选（若 API 不支持服务端筛选，则客户端兜底）
    if (lifecycleFilter && item.lifecycle !== lifecycleFilter) return false;
    // 分数范围筛选
    if (!matchesScoreRange(item.attention_score, scoreRange)) return false;
    return true;
  });

  // 按 attention_score 降序排列（若 API 不支持服务端排序，则客户端兜底）
  const sortedItems = [...filteredItems].sort((a, b) => {
    const sa = a.attention_score ?? 0;
    const sb = b.attention_score ?? 0;
    return sb - sa;
  });

  // ── 选中状态管理 ──

  const allIds = sortedItems.map(item => item.id);
  const allSelected = sortedItems.length > 0 && selectedIds.size === sortedItems.length;

  function toggleSelect(id: string) {
    setSelectedIds(prev => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  function toggleSelectAll() {
    if (allSelected) {
      setSelectedIds(new Set());
    } else {
      setSelectedIds(new Set(allIds));
    }
  }

  function clearSelection() {
    setSelectedIds(new Set());
  }

  // ── 批量操作 ──

  async function batchMarkRead() {
    setBatchBusy(true);
    const ids = Array.from(selectedIds);
    // 客户端乐观更新
    setReadIds(prev => {
      const next = new Set(prev);
      ids.forEach(id => next.add(id));
      return next;
    });
    // 尝试通过 PATCH 更新 mastered 字段
    const results = await Promise.allSettled(
      ids.map(id =>
        fetch(`/api/knowledge/items/${encodeURIComponent(id)}`, {
          method: 'PATCH',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ mastered: 100 }),
        })
      )
    );
    const failed = results.filter(r => r.status === 'rejected').length;
    if (failed > 0) {
      setError(`${failed} 个条目标记已读失败`);
    }
    setBatchBusy(false);
    clearSelection();
  }

  async function batchArchive() {
    setBatchBusy(true);
    const ids = Array.from(selectedIds);
    // 尝试通过 PATCH 设置 lifecycle = 'kl:publish' 表示归档
    const results = await Promise.allSettled(
      ids.map(id =>
        fetch(`/api/knowledge/items/${encodeURIComponent(id)}`, {
          method: 'PATCH',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ lifecycle: 'kl:publish' }),
        })
      )
    );
    const failed = results.filter(r => r.status === 'rejected').length;
    if (failed > 0) {
      setError(`${failed} 个条目归档失败`);
    } else {
      // 乐观移除已归档条目
      setItems(prev => prev.filter(item => !ids.includes(item.id)));
    }
    setBatchBusy(false);
    clearSelection();
  }

  async function batchGenerateSummary() {
    setBatchBusy(true);
    const ids = Array.from(selectedIds);
    // 筛选出没有 summary 的条目
    const noSummary = sortedItems.filter(
      item => ids.includes(item.id) && !item.summary
    );
    // 尝试触发摘要生成
    const results = await Promise.allSettled(
      noSummary.map(item =>
        fetch(`/api/knowledge/items/${encodeURIComponent(item.id)}`, {
          method: 'PATCH',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ summary: '(摘要生成中…)' }),
        })
      )
    );
    const failed = results.filter(r => r.status === 'rejected').length;
    if (failed > 0) {
      setError(`${failed} 个条目摘要生成失败`);
    }
    setBatchBusy(false);
    clearSelection();
  }

  // ── 渲染 ──

  return (
    <div className="space-y-3">
      <OnboardingHint storageKey="kb-outbox" title="整理模式">
        <p>将收藏或待整理的条目归集到知识库。</p>
      </OnboardingHint>

      {/* 顶部描述 */}
      <section
        className="rounded-[var(--radius-md)] p-3"
        style={{ backgroundColor: 'var(--bg-elevated)', border: '1px solid var(--border-color)' }}
      >
        <div className="flex items-center gap-2 mb-1.5">
          <Icon size={16}>
            <rect x="3" y="3" width="18" height="18" rx="2" ry="2" />
            <line x1="9" y1="9" x2="15" y2="15" />
            <line x1="15" y1="9" x2="9" y2="15" />
          </Icon>
          <h3 className="text-sm font-bold" style={{ color: 'var(--text-primary)' }}>
            整理模式
          </h3>
          {!loading && (
            <span className="text-[11px] font-mono" style={{ color: 'var(--text-muted)' }}>
              {sortedItems.length} 条待处理
            </span>
          )}
        </div>
        <p className="text-xs" style={{ color: 'var(--text-secondary)' }}>
          按注意力分数排序，批量处理待整理的知识条目。
        </p>
      </section>

      {/* 注意力数据不可用提示 */}
      {!loading && !error && !attentionAvailable && items.length > 0 && (
        <div
          className="rounded-[var(--radius-md)] p-3 text-xs flex items-center gap-2"
          style={{
            backgroundColor: 'color-mix(in srgb, var(--color-warning) 12%, transparent)',
            border: '1px solid var(--color-warning)',
            color: 'var(--color-warning)',
          }}
        >
          <Icon size={14}>
            <path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z" />
            <line x1="12" y1="9" x2="12" y2="13" />
            <line x1="12" y1="17" x2="12.01" y2="17" />
          </Icon>
          <span>
            注意力数据尚未采集。请运行注意力评分任务后，条目将按注意力分数排序显示。
          </span>
        </div>
      )}

      {/* 筛选栏 */}
      <section
        className="rounded-[var(--radius-md)] p-2.5 flex flex-wrap items-center gap-2"
        style={{ backgroundColor: 'var(--bg-elevated)', border: '1px solid var(--border-color)' }}
      >
        {/* 生命周期筛选 */}
        <select
          value={lifecycleFilter}
          onChange={e => setLifecycleFilter(e.target.value)}
          className="tech-select text-xs px-2 py-1"
          aria-label="按生命周期筛选"
        >
          {LIFECYCLE_OPTIONS.map(opt => (
            <option key={opt.value} value={opt.value}>{opt.label}</option>
          ))}
        </select>

        {/* 时间范围 */}
        <div className="flex items-center gap-1" role="group" aria-label="时间范围">
          {DATE_RANGE_OPTIONS.map(opt => (
            <button
              key={opt.value}
              type="button"
              onClick={() => setDateRange(opt.value)}
              className={`ink-chip text-xs ${dateRange === opt.value ? 'active' : ''}`}
              aria-pressed={dateRange === opt.value}
            >
              {opt.label}
            </button>
          ))}
        </div>

        {/* 分数范围 */}
        <select
          value={scoreRange}
          onChange={e => setScoreRange(e.target.value)}
          className="tech-select text-xs px-2 py-1"
          aria-label="按注意力分数筛选"
        >
          {SCORE_RANGE_OPTIONS.map(opt => (
            <option key={opt.value} value={opt.value}>{opt.label}</option>
          ))}
        </select>
      </section>

      {/* 错误状态 */}
      {error && (
        <div
          className="rounded-[var(--radius-md)] p-3 text-xs"
          style={{
            backgroundColor: 'color-mix(in srgb, var(--color-error) 12%, transparent)',
            border: '1px solid var(--color-error)',
            color: 'var(--color-error)',
          }}
        >
          <div className="flex items-center gap-2">
            <Icon size={14}>
              <circle cx="12" cy="12" r="10" />
              <line x1="12" y1="8" x2="12" y2="12" />
              <line x1="12" y1="16" x2="12.01" y2="16" />
            </Icon>
            {error}
            <button
              type="button"
              className="ml-auto underline hover:no-underline"
              onClick={fetchItems}
            >
              重试
            </button>
          </div>
        </div>
      )}

      {/* 加载状态 */}
      {loading && (
        <div className="flex items-center justify-center py-16">
          <div className="flex items-center gap-2 text-xs" style={{ color: 'var(--text-muted)' }}>
            <span className="inline-block w-4 h-4 border-2 border-current border-t-transparent rounded-full animate-spin" />
            加载中…
          </div>
        </div>
      )}

      {/* 空状态 */}
      {!loading && !error && sortedItems.length === 0 && (
        <EmptyState
          title="暂无待处理项目"
          description={
            lifecycleFilter || scoreRange
              ? '当前筛选条件下没有待处理的知识条目'
              : '所有知识条目已处理完毕，暂无待处理项目'
          }
          icon={
            <Icon size={20}>
              <rect x="3" y="3" width="18" height="18" rx="2" ry="2" />
              <line x1="9" y1="9" x2="15" y2="15" />
              <line x1="15" y1="9" x2="9" y2="15" />
            </Icon>
          }
        />
      )}

      {/* 全选栏 */}
      {!loading && !error && sortedItems.length > 0 && (
        <div
          className="rounded-[var(--radius-md)] px-3 py-2 flex items-center gap-3"
          style={{ backgroundColor: 'var(--bg-elevated)', border: '1px solid var(--border-color)' }}
        >
          <label className="flex items-center gap-2 text-xs cursor-pointer" style={{ color: 'var(--text-secondary)' }}>
            <input
              type="checkbox"
              checked={allSelected}
              onChange={toggleSelectAll}
              className="tech-checkbox"
              aria-label="全选"
            />
            全选 ({sortedItems.length})
          </label>
          {selectedIds.size > 0 && (
            <span className="text-xs font-mono" style={{ color: 'var(--color-info)' }}>
              已选 {selectedIds.size} 项
            </span>
          )}
        </div>
      )}

      {/* 卡片列表 */}
      {!loading && !error && sortedItems.length > 0 && (
        <div className="space-y-2">
          {sortedItems.map(item => (
            <OutboxCard
              key={item.id}
              item={item}
              selected={selectedIds.has(item.id)}
              read={readIds.has(item.id)}
              onToggleSelect={() => toggleSelect(item.id)}
            />
          ))}
        </div>
      )}

      {/* 批量操作栏 */}
      {selectedIds.size > 0 && (
        <div
          className="sticky bottom-3 rounded-[var(--radius-md)] px-3 py-2.5 flex items-center gap-2"
          style={{
            backgroundColor: 'var(--bg-elevated)',
            border: '1px solid var(--border-color)',
            boxShadow: '0 -2px 8px rgba(0,0,0,0.1)',
          }}
        >
          <span className="text-xs mr-2" style={{ color: 'var(--text-secondary)' }}>
            已选 {selectedIds.size} 项
          </span>
          <button
            type="button"
            className="btn-ghost text-xs px-2.5 py-1.5 rounded-[var(--radius-sm)]"
            style={{ color: 'var(--color-info)' }}
            onClick={batchMarkRead}
            disabled={batchBusy}
          >
            <Icon size={12}>
              <polyline points="20 6 9 17 4 12" />
            </Icon>
            标记已读
          </button>
          <button
            type="button"
            className="btn-ghost text-xs px-2.5 py-1.5 rounded-[var(--radius-sm)]"
            style={{ color: 'var(--color-warning)' }}
            onClick={batchArchive}
            disabled={batchBusy}
          >
            <Icon size={12}>
              <polyline points="21 19 21 5 3 5 3 19" />
              <line x1="9" y1="9" x2="15" y2="15" />
              <line x1="15" y1="9" x2="9" y2="15" />
            </Icon>
            归档
          </button>
          <button
            type="button"
            className="btn-ghost text-xs px-2.5 py-1.5 rounded-[var(--radius-sm)]"
            style={{ color: 'var(--color-success)' }}
            onClick={batchGenerateSummary}
            disabled={batchBusy}
          >
            <Icon size={12}>
              <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
              <polyline points="14 2 14 8 20 8" />
              <line x1="16" y1="13" x2="8" y2="13" />
              <line x1="16" y1="17" x2="8" y2="17" />
            </Icon>
            生成摘要
          </button>
          <button
            type="button"
            className="ml-auto btn-ghost text-xs px-2 py-1 rounded-[var(--radius-sm)]"
            style={{ color: 'var(--text-muted)' }}
            onClick={clearSelection}
          >
            取消
          </button>
        </div>
      )}
    </div>
  );
}

// ── 子组件: 单张卡片 ──────────────────────────────────────────

interface OutboxCardProps {
  item: OutboxKnowledgeItem;
  selected: boolean;
  read: boolean;
  onToggleSelect: () => void;
}

function OutboxCard({ item, selected, read, onToggleSelect }: OutboxCardProps) {
  const score = item.attention_score ?? 0;
  const scoreColor = getAttentionColor(score);
  const lifecycleColor = item.lifecycle
    ? getLifecycleColor(item.lifecycle)
    : 'var(--text-muted)';
  const lifecycleLabel = item.lifecycle
    ? getLifecycleLabel(item.lifecycle)
    : '--';

  return (
    <article
      className="rounded-[var(--radius-md)] transition-all duration-150"
      style={{
        backgroundColor: read
          ? 'color-mix(in srgb, var(--bg-elevated) 60%, transparent)'
          : 'var(--bg-elevated)',
        border: selected
          ? '1px solid var(--color-info)'
          : '1px solid var(--border-color)',
        opacity: read ? 0.6 : 1,
      }}
    >
      <div className="flex items-start gap-3 p-3">
        {/* 复选框 */}
        <div className="pt-0.5">
          <input
            type="checkbox"
            checked={selected}
            onChange={onToggleSelect}
            className="tech-checkbox"
            aria-label={`选择 ${item.title}`}
          />
        </div>

        {/* 内容区 */}
        <div className="flex-1 min-w-0">
          {/* 顶部徽标行 */}
          <div className="flex items-center gap-2 mb-1.5">
            {/* 注意力分圆形徽标 */}
            <span
              className="inline-flex items-center justify-center w-5 h-5 rounded-full text-[9px] font-bold font-mono"
              style={{
                backgroundColor: `color-mix(in srgb, ${scoreColor} 20%, transparent)`,
                color: scoreColor,
                border: `1px solid color-mix(in srgb, ${scoreColor} 40%, transparent)`,
              }}
              title={`注意力分: ${score}`}
            >
              {score}
            </span>

            {/* 生命周期阶段标签 */}
            <span
              className="text-[10px] px-1.5 py-0.5 rounded font-mono"
              style={{
                backgroundColor: `color-mix(in srgb, ${lifecycleColor} 15%, transparent)`,
                color: lifecycleColor,
              }}
            >
              {lifecycleLabel}
            </span>

            {/* 录入日期 */}
            {item.ingested_at && (
              <span className="text-[10px] ml-auto" style={{ color: 'var(--text-muted)' }}>
                {new Date(item.ingested_at).toLocaleDateString('zh-CN', {
                  month: 'short',
                  day: 'numeric',
                })}
              </span>
            )}
          </div>

          {/* 标题 */}
          <h3
            className="text-sm font-semibold leading-snug mb-1"
            style={{ color: read ? 'var(--text-secondary)' : 'var(--text-primary)' }}
          >
            {item.source_url ? (
              <a
                href={item.source_url}
                target="_blank"
                rel="noopener noreferrer"
                className="focus-ring hover:underline"
                style={{ color: 'inherit' }}
              >
                {item.title}
              </a>
            ) : (
              <span>{item.title}</span>
            )}
          </h3>

          {/* 摘要 */}
          {item.summary && (
            <p
              className="text-xs leading-relaxed line-clamp-2"
              style={{ color: 'var(--text-secondary)' }}
            >
              {item.summary}
            </p>
          )}

          {/* 领域标签 */}
          {item.domain && (
            <div className="flex flex-wrap gap-1 mt-1.5">
              <span
                className="text-[9px] px-1.5 py-0.5 rounded"
                style={{
                  backgroundColor: 'color-mix(in srgb, var(--color-info) 8%, transparent)',
                  color: 'var(--color-info)',
                }}
              >
                {item.domain}
              </span>
            </div>
          )}
        </div>
      </div>
    </article>
  );
}