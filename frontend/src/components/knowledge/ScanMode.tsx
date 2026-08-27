/**
 * ScanMode — 快速扫描模式 (Phase 13)
 *
 * 增强版知识条目列表视图，支持多维筛选:
 *  - 领域 (domain) 筛选
 *  - 生命周期 (lifecycle) 筛选
 *  - 标签 (tags) 客户端筛选
 *  - 时间范围 (ingested_at) 筛选
 *
 * 路由: /knowledge/scan
 */
import { useState, useEffect, useCallback } from 'react';
import { Icon } from '../Icon';
import { EmptyState } from '../EmptyState';
import { STAGE_LABELS, STAGE_COLORS, ALL_STAGES } from './LifecycleProgress';
import { getCategoryColorVar, getCategoryLabel } from '../../types';
import { OnboardingHint } from '../layout/OnboardingHint';
import type { KnowledgeItem } from '../../types';

// ── 扩展类型: 后端 to_dict() 返回的额外字段 ──────────────────

interface ScanKnowledgeItem extends KnowledgeItem {
  lifecycle?: string;
  news_type?: string;
  tech_stack?: string[];
  attention_score?: number;
}

// ── 常量 ──────────────────────────────────────────────────────

const TIME_RANGES = [
  { value: 'H24', label: '24小时' },
  { value: 'D3', label: '3天' },
  { value: 'D7', label: '7天' },
  { value: 'D30', label: '30天' },
] as const;

const DOMAIN_OPTIONS = [
  { value: '', label: '全部分类' },
  { value: 'security', label: '网络安全' },
  { value: 'ai', label: '科技 / AI' },
  { value: 'finance', label: '金融 / 投资' },
  { value: 'startup', label: '独立开发 / 创业' },
  { value: 'github', label: 'GitHub 项目' },
  { value: 'bid', label: '招标资讯' },
  { value: 'general', label: '通用' },
];

const LIFECYCLE_OPTIONS = [
  { value: '', label: '全部阶段' },
  ...ALL_STAGES.map(s => ({ value: s, label: STAGE_LABELS[s] || s })),
];

// ── 工具函数 ──────────────────────────────────────────────────

/** 根据时间范围值计算 since ISO 字符串 */
function timeRangeToSince(range: string): string {
  const now = Date.now();
  const ms: Record<string, number> = {
    H24: 24 * 60 * 60 * 1000,
    D3: 3 * 24 * 60 * 60 * 1000,
    D7: 7 * 24 * 60 * 60 * 1000,
    D30: 30 * 24 * 60 * 60 * 1000,
  };
  const offset = ms[range] || 0;
  return new Date(now - offset).toISOString();
}

/** 根据 attention_score 返回对应颜色 */
function getAttentionColor(score: number): string {
  if (score <= 20) return 'var(--text-muted)';
  if (score <= 40) return 'var(--color-info)';
  if (score <= 60) return 'var(--color-success)';
  if (score <= 80) return 'var(--color-warning)';
  return 'var(--color-error)';
}

// ── 主组件 ────────────────────────────────────────────────────

export function ScanMode() {
  // 筛选状态
  const [domain, setDomain] = useState('');
  const [lifecycle, setLifecycle] = useState('');
  const [timeRange, setTimeRange] = useState('D7');
  const [tagFilter, setTagFilter] = useState('');

  // 数据状态
  const [items, setItems] = useState<ScanKnowledgeItem[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // ── 数据加载 ──

  const fetchItems = useCallback(() => {
    setLoading(true);
    setError(null);

    const params = new URLSearchParams();
    params.set('limit', '50');
    if (domain) params.set('domain', domain);
    if (lifecycle) params.set('lifecycle', lifecycle);
    if (timeRange) params.set('since', timeRangeToSince(timeRange));

    fetch(`/api/knowledge/items?${params.toString()}`)
      .then(async r => {
        if (!r.ok) throw new Error(`请求失败 (${r.status})`);
        const data = await r.json();
        return data;
      })
      .then(data => {
        setItems(data.items || []);
        setTotal(data.total || 0);
      })
      .catch(e => {
        setError(e?.message || '加载失败');
        setItems([]);
        setTotal(0);
      })
      .finally(() => {
        setLoading(false);
      });
  }, [domain, lifecycle, timeRange]);

  useEffect(() => {
    fetchItems();
  }, [fetchItems]);

  // ── 客户端标签过滤 ──

  const filteredItems = tagFilter.trim()
    ? items.filter(item =>
        item.tags?.some(t => t.toLowerCase().includes(tagFilter.toLowerCase()))
      )
    : items;

  // ── 渲染 ──

  return (
    <div className="space-y-3">
      <OnboardingHint storageKey="kb-scan" title="扫描模式">
        <p>快速扫描知识库新内容，发现感兴趣的条目。</p>
      </OnboardingHint>

      {/* 顶部描述 */}
      <section
        className="rounded-[var(--radius-md)] p-3"
        style={{ backgroundColor: 'var(--bg-elevated)', border: '1px solid var(--border-color)' }}
      >
        <div className="flex items-center gap-2 mb-1.5">
          <Icon size={16}>
            <circle cx="12" cy="12" r="9" />
            <path d="M12 7v10M7 12h10" />
          </Icon>
          <h3 className="text-sm font-bold" style={{ color: 'var(--text-primary)' }}>
            快速扫描
          </h3>
          {!loading && (
            <span className="text-[11px] font-mono" style={{ color: 'var(--text-muted)' }}>
              {filteredItems.length} / {total} 条
            </span>
          )}
        </div>
        <p className="text-xs" style={{ color: 'var(--text-secondary)' }}>
          多维筛选知识条目，快速浏览最新入库内容。
        </p>
      </section>

      {/* 筛选栏 */}
      <section
        className="rounded-[var(--radius-md)] p-2.5 flex flex-wrap items-center gap-2"
        style={{ backgroundColor: 'var(--bg-elevated)', border: '1px solid var(--border-color)' }}
      >
        {/* 领域筛选 */}
        <select
          value={domain}
          onChange={e => setDomain(e.target.value)}
          className="tech-select text-xs px-2 py-1"
          aria-label="按分类筛选"
        >
          {DOMAIN_OPTIONS.map(opt => (
            <option key={opt.value} value={opt.value}>{opt.label}</option>
          ))}
        </select>

        {/* 生命周期筛选 */}
        <select
          value={lifecycle}
          onChange={e => setLifecycle(e.target.value)}
          className="tech-select text-xs px-2 py-1"
          aria-label="按生命周期筛选"
        >
          {LIFECYCLE_OPTIONS.map(opt => (
            <option key={opt.value} value={opt.value}>{opt.label}</option>
          ))}
        </select>

        {/* 时间范围按钮组 */}
        <div className="flex items-center gap-1" role="group" aria-label="时间范围">
          {TIME_RANGES.map(tr => (
            <button
              key={tr.value}
              type="button"
              onClick={() => setTimeRange(tr.value)}
              className={`ink-chip text-xs ${timeRange === tr.value ? 'active' : ''}`}
              aria-pressed={timeRange === tr.value}
            >
              {tr.label}
            </button>
          ))}
        </div>

        {/* 标签筛选输入 */}
        <div className="relative flex-1 min-w-[120px] max-w-[180px]">
          <input
            type="text"
            value={tagFilter}
            onChange={e => setTagFilter(e.target.value)}
            placeholder="标签筛选…"
            className="tech-input text-xs px-2 py-1 w-full"
            aria-label="按标签筛选"
          />
          {tagFilter && (
            <button
              type="button"
              className="absolute right-1.5 top-1/2 -translate-y-1/2 flex items-center justify-center"
              style={{ color: 'var(--text-muted)' }}
              onClick={() => setTagFilter('')}
              aria-label="清除标签筛选"
            >
              <Icon size={12}>
                <line x1="18" y1="6" x2="6" y2="18" />
                <line x1="6" y1="6" x2="18" y2="18" />
              </Icon>
            </button>
          )}
        </div>
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
      {!loading && !error && filteredItems.length === 0 && (
        <EmptyState
          title="无匹配条目"
          description={
            tagFilter
              ? `没有包含标签 "${tagFilter}" 的知识条目`
              : '当前筛选条件下没有知识条目'
          }
          icon={
            <Icon size={20}>
              <circle cx="11" cy="11" r="8" />
              <line x1="21" y1="21" x2="16.65" y2="16.65" />
              <line x1="8" y1="11" x2="14" y2="11" />
            </Icon>
          }
        />
      )}

      {/* 卡片网格 */}
      {!loading && !error && filteredItems.length > 0 && (
        <div className="agihunt-card-grid">
          {filteredItems.map((item, index) => (
            <ScanCard key={item.id} item={item} index={index} />
          ))}
        </div>
      )}
    </div>
  );
}

// ── 子组件: 单张卡片 ──────────────────────────────────────────

interface ScanCardProps {
  item: ScanKnowledgeItem;
  index: number;
}

function ScanCard({ item, index }: ScanCardProps) {
  const domainColor = item.domain ? getCategoryColorVar(item.domain) : 'var(--text-muted)';
  const lifecycleColor = item.lifecycle
    ? (STAGE_COLORS[item.lifecycle] || 'var(--text-muted)')
    : 'var(--text-muted)';
  const lifecycleLabel = item.lifecycle
    ? (STAGE_LABELS[item.lifecycle] || item.lifecycle)
    : '--';
  const delayClass = `delay-${Math.min(index + 1, 10)}`;

  return (
    <article className={`agihunt-card animate-fade-in-up ${delayClass}`}>
      {/* 顶部: 分类 + 生命周期徽标 */}
      <div className="agihunt-card-header">
        <span
          className="agihunt-card-badge"
          style={{
            color: domainColor,
            borderColor: `color-mix(in srgb, ${domainColor} 40%, transparent)`,
          }}
        >
          {getCategoryLabel(item.domain || '') || item.domain || '未分类'}
        </span>
        <span
          className="text-[10px] px-1.5 py-0.5 rounded font-mono"
          style={{
            backgroundColor: `color-mix(in srgb, ${lifecycleColor} 15%, transparent)`,
            color: lifecycleColor,
          }}
        >
          {lifecycleLabel}
        </span>
        {/* Attention score badge */}
        {item.attention_score && item.attention_score > 0 && (
          <span
            className="text-[9px] px-1.5 py-0.5 rounded font-mono ml-auto"
            style={{
              backgroundColor: `color-mix(in srgb, ${getAttentionColor(item.attention_score)} 15%, transparent)`,
              color: getAttentionColor(item.attention_score),
              border: `1px solid color-mix(in srgb, ${getAttentionColor(item.attention_score)} 30%, transparent)`,
            }}
            title="注意力分"
          >
            {item.attention_score}
          </span>
        )}
      </div>

      {/* 标题 */}
      <h3 className="agihunt-card-title">
        {item.source_url ? (
          <a
            href={item.source_url}
            target="_blank"
            rel="noopener noreferrer"
            className="focus-ring"
          >
            {item.title}
          </a>
        ) : (
          <span>{item.title}</span>
        )}
      </h3>

      {/* 摘要: 类型 + 难度作为摘要代用 */}
      <div className="flex flex-wrap gap-1.5 mb-2">
        {item.type && (
          <span
            className="text-[10px] px-1.5 py-0.5 rounded"
            style={{
              backgroundColor: 'color-mix(in srgb, var(--text-muted) 10%, transparent)',
              color: 'var(--text-secondary)',
            }}
          >
            {item.type}
          </span>
        )}
        {item.difficulty && (
          <span
            className="text-[10px] px-1.5 py-0.5 rounded"
            style={{
              backgroundColor: 'color-mix(in srgb, var(--text-muted) 10%, transparent)',
              color: 'var(--text-secondary)',
            }}
          >
            {item.difficulty}
          </span>
        )}
      </div>

      {/* 标签 (最多显示 4 个) */}
      {item.tags && item.tags.length > 0 && (
        <div className="flex flex-wrap gap-1 mb-2">
          {item.tags.slice(0, 4).map(tag => (
            <span
              key={tag}
              className="text-[9px] px-1 py-0.5 rounded"
              style={{
                backgroundColor: 'color-mix(in srgb, var(--color-info) 8%, transparent)',
                color: 'var(--color-info)',
              }}
            >
              {tag}
            </span>
          ))}
          {item.tags.length > 4 && (
            <span className="text-[9px]" style={{ color: 'var(--text-muted)' }}>
              +{item.tags.length - 4}
            </span>
          )}
        </div>
      )}

      {/* 底部: 来源 + 录入日期 + 掌握度 */}
      <div className="agihunt-card-footer">
        <div className="agihunt-card-meta">
          {item.source && (
            <span className="agihunt-card-source" style={{ color: 'var(--text-muted)' }}>
              {item.source}
            </span>
          )}
          {item.ingested_at && (
            <span className="text-[10px]" style={{ color: 'var(--text-muted)' }}>
              {new Date(item.ingested_at).toLocaleDateString('zh-CN', {
                month: 'short',
                day: 'numeric',
              })}
            </span>
          )}
        </div>

        {/* 掌握度进度条 */}
        {item.mastery !== undefined && item.mastery > 0 && (
          <div className="flex items-center gap-1">
            <div
              className="h-1.5 w-12 rounded-full overflow-hidden"
              style={{ backgroundColor: 'var(--border-color)' }}
            >
              <div
                className="h-full rounded-full transition-all duration-300"
                style={{
                  width: `${Math.min(100, item.mastery)}%`,
                  backgroundColor:
                    item.mastery >= 80
                      ? 'var(--color-success)'
                      : item.mastery >= 50
                        ? 'var(--color-warning)'
                        : 'var(--color-info)',
                }}
              />
            </div>
            <span className="text-[10px] font-mono" style={{ color: 'var(--text-muted)' }}>
              {item.mastery}%
            </span>
          </div>
        )}
      </div>
    </article>
  );
}
