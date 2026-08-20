/**
 * BriefingMode — 简报模式
 *
 * Phase 13: 每日简报
 * 展示最近发布的 knowledge 条目 (lifecycle=kl:publish)，
 * 附带数据源健康状态概览。
 */
import React, { useState, useEffect } from 'react';
import { Icon } from '../Icon';
import { useDigest } from '../../hooks/useDigest';
import { AttentionHeatmap } from './AttentionHeatmap';
import { OnboardingHint } from '../layout/OnboardingHint';

const SOURCE_LABELS: Record<string, string> = {
  cubox: 'Cubox',
  bookmark: '书签',
  secnews: '实时资讯',
  secnews_archive: '归档',
};

function formatDate(iso: string): string {
  if (!iso) return '';
  const d = new Date(iso);
  const pad = (n: number) => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
}

function isToday(iso: string): boolean {
  if (!iso) return false;
  const d = new Date(iso);
  const now = new Date();
  return (
    d.getFullYear() === now.getFullYear() &&
    d.getMonth() === now.getMonth() &&
    d.getDate() === now.getDate()
  );
}

interface BriefingItem {
  id: string;
  title: string;
  source: string;
  source_url: string;
  domain: string | null;
  topic: string | null;
  tags: string[];
  concepts: string[];
  mastered: number;
  lifecycle: string;
  ingested_at: string;
  updated_at: string;
}

interface SourceHealth {
  category: string;
  source_name: string;
  status: string;
  total_items: number;
  last_checked_at: string | null;
  last_error: string | null;
}

export function BriefingMode() {
  const [items, setItems] = useState<BriefingItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [health, setHealth] = useState<SourceHealth[]>([]);
  const [healthLoading, setHealthLoading] = useState(true);

  const [chunkSummaries, setChunkSummaries] = useState<Record<string, string>>({});

  // P1.4: 集成官方每日简报 (digest) — 原 /brief 路由功能合并到此
  const { digest, loading: digestLoading, error: digestError, refresh: refreshDigest, generate: generateDigest, markRead: markDigestRead } = useDigest();

  const handleGenerateDigest = async () => {
    await generateDigest();
    await markDigestRead();
    await refreshDigest();
  };

  useEffect(() => {
    setLoading(true);
    setError(null);
    fetch('/api/knowledge/items?lifecycle=kl:publish&limit=20')
      .then(r => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        return r.json();
      })
      .then(data => {
        const all = (data.items || []) as BriefingItem[];
        // 后端暂不支持 lifecycle 查询参数，前端过滤
        const published = all.filter(
          (item: BriefingItem) => item.lifecycle === 'kl:publish'
        );
        setItems(published);
        setLoading(false);
      })
      .catch(e => {
        setError(e?.message || String(e));
        setLoading(false);
      });
  }, []);

  useEffect(() => {
    setHealthLoading(true);
    fetch('/api/sources/health')
      .then(r => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        return r.json();
      })
      .then(data => {
        setHealth(data.sources || []);
        setHealthLoading(false);
      })
      .catch(() => {
        // 健康状态非关键数据，静默失败
        setHealthLoading(false);
      });
  }, []);

  // 加载每个条目的第一个 chunk 摘要
  useEffect(() => {
    if (items.length === 0) return;
    let cancelled = false;

    // 最多取前 10 条的 chunks，避免过多请求
    Promise.all(
      items.slice(0, 10).map(item =>
        fetch(`/api/knowledge/chunks/${encodeURIComponent(item.id)}`)
          .then(r => (r.ok ? r.json() : { chunks: [] }))
          .then(data => ({ id: item.id, summary: (data.chunks?.[0] as { summary?: string })?.summary || '' }))
          .catch(() => ({ id: item.id, summary: '' }))
      )
    ).then(results => {
      if (cancelled) return;
      const map: Record<string, string> = {};
      results.forEach(r => {
        if (r.summary) map[r.id] = r.summary;
      });
      setChunkSummaries(map);
    });

    return () => { cancelled = true; };
  }, [items]);

  const todayItems = items.filter(item => isToday(item.updated_at));
  const earlierItems = items.filter(item => !isToday(item.updated_at));

  const activeCount = health.filter(h => h.status === 'active').length;
  const staleCount = health.filter(h => h.status === 'stale').length;
  const deadCount = health.filter(h => h.status === 'dead').length;

  return (
    <div className="space-y-4" data-area-page="briefing">
      <OnboardingHint storageKey="kb-briefing" title="简报模式">
        <p>展示今日知识库已发布条目与官方每日简报。</p>
      </OnboardingHint>

      {/* 顶部 hero */}
      <section
        className="rounded-[var(--radius-md)] p-3.5"
        style={{
          backgroundColor: 'var(--bg-elevated)',
          border: '1px solid var(--border-color)',
          borderLeft: '3px solid var(--color-info)',
        }}
      >
        <div className="flex items-start gap-3">
          <div
            className="w-9 h-9 rounded-md flex items-center justify-center shrink-0"
            style={{
              backgroundColor: 'color-mix(in srgb, var(--color-info) 12%, transparent)',
              color: 'var(--color-info)',
            }}
          >
            <Icon size={18}>
              <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
              <polyline points="14 2 14 8 20 8" />
              <line x1="16" y1="13" x2="8" y2="13" />
              <line x1="16" y1="17" x2="8" y2="17" />
              <polyline points="10 9 9 9 8 9" />
            </Icon>
          </div>
          <div className="flex-1 min-w-0">
            <h3 className="text-sm font-bold mb-0.5" style={{ color: 'var(--text-primary)' }}>
              简报模式 · 今日知识发布
            </h3>
            <p className="text-xs leading-relaxed" style={{ color: 'var(--text-secondary)' }}>
              展示最近发布的已编译知识条目，快速掌握今日知识库更新动态。
            </p>
          </div>
        </div>
      </section>

      {/* P1.4: 官方每日简报 (digest) — 合并自原 /brief 路由 */}
      <section
        className="rounded-[var(--radius-md)] p-3.5"
        style={{
          backgroundColor: 'var(--bg-elevated)',
          border: '1px solid var(--border-color)',
          borderLeft: '3px solid var(--accent)',
        }}
      >
        <div className="flex items-center justify-between mb-2">
          <h4
            className="text-xs font-semibold flex items-center gap-2"
            style={{ color: 'var(--text-primary)' }}
          >
            <Icon size={12}>
              <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
              <polyline points="14 2 14 8 20 8" />
            </Icon>
            官方每日简报
          </h4>
          <button
            type="button"
            onClick={handleGenerateDigest}
            className="btn-secondary"
            title="手动生成昨日简报"
          >
            ⟳ 生成
          </button>
        </div>

        {digestLoading && (
          <p className="text-[11px]" style={{ color: 'var(--text-muted)' }}>加载简报…</p>
        )}

        {digestError && (
          <p className="text-[11px]" style={{ color: 'var(--color-error)' }} role="alert">
            {digestError}
          </p>
        )}

        {!digestLoading && !digestError && !digest && (
          <p className="text-[11px]" style={{ color: 'var(--text-muted)' }}>
            暂无每日简报 — 点击右上角「生成」手动创建
          </p>
        )}

        {!digestLoading && !digestError && digest && (
          <div>
            <div className="flex items-center gap-2 mb-1.5">
              <span
                className="text-[10px] font-mono uppercase px-1.5 py-0.5 rounded"
                style={{
                  backgroundColor: 'color-mix(in srgb, var(--accent) 9%, transparent)',
                  color: 'var(--accent)',
                }}
              >
                {digest.period}
              </span>
              <span className="text-[10px] font-mono" style={{ color: 'var(--text-muted)' }}>
                {new Date(digest.created_at).toLocaleString('zh-CN')}
              </span>
              <button
                type="button"
                className="btn-ghost ml-auto text-[10px]"
                onClick={async () => { await markDigestRead(); await refreshDigest(); }}
                style={{ minHeight: 'auto', padding: '2px 8px' }}
              >
                标记已读
              </button>
            </div>
            <p className="text-[12px] leading-relaxed" style={{ color: 'var(--text-primary)' }}>
              {digest.summary}
            </p>
            {typeof digest.count === 'number' && (
              <p className="text-[10px] mt-1" style={{ color: 'var(--text-muted)' }}>
                昨日共 {digest.count} 篇文章
              </p>
            )}
          </div>
        )}
      </section>

      {/* 数据源健康状态 */}
      <section
        className="rounded-[var(--radius-md)] p-3"
        style={{ backgroundColor: 'var(--bg-elevated)', border: '1px solid var(--border-color)' }}
      >
        <h4
          className="text-xs font-semibold flex items-center gap-2 mb-2"
          style={{ color: 'var(--text-primary)' }}
        >
          <Icon size={12}>
            <circle cx="12" cy="12" r="10" />
            <path d="M12 8v4M12 16h.01" />
          </Icon>
          数据源健康状态
        </h4>
        {healthLoading ? (
          <p className="text-[10px]" style={{ color: 'var(--text-muted)' }}>加载中…</p>
        ) : health.length === 0 ? (
          <p className="text-[10px]" style={{ color: 'var(--text-muted)' }}>暂无健康数据</p>
        ) : (
          <div className="flex items-center gap-3 text-[11px]">
            <span style={{ color: 'var(--color-success)' }}>
              ● {activeCount} 活跃
            </span>
            <span style={{ color: 'var(--color-warning)' }}>
              ● {staleCount} 停滞
            </span>
            <span style={{ color: 'var(--color-error)' }}>
              ● {deadCount} 失效
            </span>
            <span style={{ color: 'var(--text-muted)' }}>
              共 {health.length} 源
            </span>
          </div>
        )}
      </section>

      {/* 注意力热力图 */}
      <section
        className="rounded-[var(--radius-md)]"
        style={{ backgroundColor: 'var(--bg-elevated)', border: '1px solid var(--border-color)', overflow: 'hidden' }}
      >
        <AttentionHeatmap compact />
      </section>

      {/* Loading */}
      {loading && (
        <div
          className="rounded-[var(--radius-md)] p-4 text-center"
          style={{ backgroundColor: 'var(--bg-elevated)', border: '1px solid var(--border-color)' }}
        >
          <p className="text-xs" style={{ color: 'var(--text-muted)' }}>
            加载知识条目…
          </p>
        </div>
      )}

      {/* Error */}
      {error && (
        <div
          className="rounded-[var(--radius-md)] p-2.5 text-xs"
          style={{
            backgroundColor: 'color-mix(in srgb, var(--color-error) 12%, transparent)',
            border: '1px solid var(--color-error)',
            color: 'var(--color-error)',
          }}
        >
          加载失败: {error}
        </div>
      )}

      {/* Empty state */}
      {!loading && !error && items.length === 0 && (
        <div
          className="rounded-[var(--radius-md)] p-6 text-center"
          style={{ backgroundColor: 'var(--bg-elevated)', border: '1px solid var(--border-color)' }}
        >
          <div
            className="w-10 h-10 rounded-full flex items-center justify-center mx-auto mb-3"
            style={{
              backgroundColor: 'color-mix(in srgb, var(--color-info) 10%, transparent)',
              color: 'var(--color-info)',
            }}
          >
            <Icon size={20}>
              <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
              <polyline points="14 2 14 8 20 8" />
            </Icon>
          </div>
          <p className="text-sm font-medium mb-1" style={{ color: 'var(--text-primary)' }}>
            今日暂无已发布条目
          </p>
          <p className="text-xs" style={{ color: 'var(--text-secondary)' }}>
            切换到「扫描模式」采集新内容，或等待知识库编译任务完成。
          </p>
        </div>
      )}

      {/* Today's items */}
      {!loading && !error && todayItems.length > 0 && (
        <section>
          <h4
            className="text-xs font-semibold flex items-center gap-2 mb-2"
            style={{ color: 'var(--text-primary)' }}
          >
            <Icon size={12}>
              <rect x="3" y="4" width="18" height="18" rx="2" ry="2" />
              <line x1="16" y1="2" x2="16" y2="6" />
              <line x1="8" y1="2" x2="8" y2="6" />
              <line x1="3" y1="10" x2="21" y2="10" />
            </Icon>
            今日发布
            <span className="text-[10px] font-mono" style={{ color: 'var(--text-muted)' }}>
              {todayItems.length} 条
            </span>
          </h4>
          <div className="space-y-2">
            {todayItems.map(item => renderCard(item))}
          </div>
        </section>
      )}

      {/* Earlier items */}
      {!loading && !error && earlierItems.length > 0 && (
        <section>
          <h4
            className="text-xs font-semibold flex items-center gap-2 mb-2"
            style={{ color: 'var(--text-primary)' }}
          >
            <Icon size={12}>
              <circle cx="12" cy="12" r="10" />
              <polyline points="12 6 12 12 16 14" />
            </Icon>
            近期发布
            <span className="text-[10px] font-mono" style={{ color: 'var(--text-muted)' }}>
              {earlierItems.length} 条
            </span>
          </h4>
          <div className="space-y-2">
            {earlierItems.map(item => renderCard(item))}
          </div>
        </section>
      )}
    </div>
  );

  function renderCard(item: BriefingItem) {
    const sourceLabel = SOURCE_LABELS[item.source] || item.source;
    // 用 tags 作为内容预览
    const preview = item.tags.length > 0
      ? item.tags.slice(0, 5).join(' · ')
      : item.concepts.slice(0, 3).join(' · ') || '暂无摘要';

    return (
      <div
        key={item.id}
        className="rounded-[var(--radius-md)] p-3"
        style={{
          backgroundColor: 'var(--bg-elevated)',
          border: '1px solid var(--border-color)',
        }}
      >
        <div className="flex items-start justify-between gap-3 mb-1.5">
          <h4
            className="text-sm font-bold leading-snug flex-1 min-w-0"
            style={{ color: 'var(--text-primary)' }}
          >
            {item.source_url ? (
              <a
                href={item.source_url}
                target="_blank"
                rel="noopener noreferrer"
                className="hover:underline focus-ring"
                style={{ color: 'inherit' }}
              >
                {item.title}
              </a>
            ) : (
              item.title
            )}
          </h4>
          {/* Score badge */}
          <span
            className="shrink-0 text-[10px] font-mono tabular-nums px-1.5 py-0.5 rounded"
            style={{
              backgroundColor: 'color-mix(in srgb, var(--color-info) 10%, transparent)',
              color: 'var(--color-info)',
              border: '1px solid color-mix(in srgb, var(--color-info) 30%, transparent)',
            }}
            title="掌握度评分"
          >
            {item.mastered}
          </span>
        </div>

        {/* Chunk 摘要 */}
        {chunkSummaries[item.id] && (
          <div className="mb-2 text-[11px] leading-relaxed" style={{ color: 'var(--text-secondary)' }}>
            <span className="text-[9px] font-mono uppercase tracking-wider" style={{ color: 'var(--text-muted)' }}>
              摘要
            </span>
            <p className="mt-0.5 line-clamp-2">{chunkSummaries[item.id]}</p>
          </div>
        )}

        {/* Preview */}
        <p
          className="text-[11px] leading-relaxed mb-2 truncate"
          style={{ color: 'var(--text-secondary)' }}
          title={preview}
        >
          {preview}
        </p>

        {/* Meta row */}
        <div className="flex items-center gap-2 text-[10px] flex-wrap" style={{ color: 'var(--text-muted)' }}>
          <span
            className="px-1.5 py-0.5 rounded-[var(--radius-sm)]"
            style={{
              backgroundColor: 'color-mix(in srgb, var(--color-info) 8%, transparent)',
              color: 'var(--color-info)',
            }}
          >
            {sourceLabel}
          </span>
          {item.domain && (
            <>
              <span aria-hidden="true">·</span>
              <span>{item.domain}</span>
            </>
          )}
          <span aria-hidden="true">·</span>
          <span className="font-mono">{formatDate(item.updated_at)}</span>
        </div>
      </div>
    );
  }
}