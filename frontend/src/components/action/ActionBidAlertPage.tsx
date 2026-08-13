/**
 * ActionBidAlertPage — 行动层 · 标书提醒与竞品分析
 *
 * 显示标书摘要、地区分布、竞品热词分析、最近标讯列表。
 * 路由: /action/bid-alert
 */
import React, { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { Icon } from '../Icon';

/* ─── 类型 ─── */

interface BidSummary {
  new_today: number;
  total_open: number;
  total_all: number;
  region_distribution: Record<string, number>;
  status_distribution: Record<string, number>;
  summary_date: string;
}

interface CompetitorKeyword {
  keyword: string;
  count: number;
}

interface CompetitorAnalysis {
  total_items: number;
  top_keywords: CompetitorKeyword[];
  region_distribution: Record<string, number>;
  analysis_date: string;
}

interface RecentBid {
  id: string;
  title: string;
  source?: string;
  url?: string;
  region?: string;
  bid_status?: string;
  published_at?: string;
}

/* ─── 主组件 ─── */

export function ActionBidAlertPage() {
  const navigate = useNavigate();
  const [summary, setSummary] = useState<BidSummary | null>(null);
  const [competitors, setCompetitors] = useState<CompetitorAnalysis | null>(null);
  const [recent, setRecent] = useState<RecentBid[]>([]);
  const [loading, setLoading] = useState(true);
  const [tab, setTab] = useState<'summary' | 'competitors' | 'recent'>('summary');

  const loadAll = useCallback(async () => {
    setLoading(true);
    try {
      const [summaryR, compR, recentR] = await Promise.all([
        fetch('/api/bid-alert/summary'),
        fetch('/api/bid-alert/competitors?limit=500&top_n=15'),
        fetch('/api/bid-alert/recent?limit=30'),
      ]);
      if (summaryR.ok) setSummary(await summaryR.json());
      if (compR.ok) setCompetitors(await compR.json());
      if (recentR.ok) {
        const data = await recentR.json();
        setRecent(data.items || []);
      }
    } catch { /* 静默 */ }
    setLoading(false);
  }, []);

  useEffect(() => { loadAll(); }, [loadAll]);

  return (
    <div className="min-h-[50vh]">
      {/* 页面头部 */}
      <div className="flex items-center gap-3 mb-4 pb-3" style={{ borderBottom: '2px solid var(--text-primary)' }}>
        <button
          onClick={() => navigate('/action')}
          className="btn-ghost px-2.5 py-1.5 text-xs"
          title="返回行动层"
          aria-label="返回行动层"
        >
          <Icon size={14}>
            <line x1="19" y1="12" x2="5" y2="12" />
            <polyline points="12 19 5 12 12 5" />
          </Icon>
          返回
        </button>
        <h2 className="font-serif text-base font-bold" style={{ color: 'var(--text-primary)' }}>
          标书提醒与竞品分析
        </h2>
        <span className="text-xs" style={{ color: 'var(--text-muted)' }}>
          行动层 · 投标情报
        </span>
      </div>

      {/* Tab 切换 */}
      <div className="flex items-center gap-2 mb-4">
        {[
          { key: 'summary' as const, label: '标书摘要' },
          { key: 'competitors' as const, label: '竞品热词' },
          { key: 'recent' as const, label: '最近标讯' },
        ].map(t => {
          const active = t.key === tab;
          return (
            <button
              key={t.key}
              onClick={() => setTab(t.key)}
              className="ink-chip focus-ring transition-colors"
              style={{
                padding: '3px 9px',
                color: active ? 'var(--text-on-light)' : 'var(--text-secondary)',
                backgroundColor: active ? 'var(--accent)' : 'var(--bg-hover)',
                borderColor: active ? 'var(--accent)' : 'var(--border-color)',
                fontWeight: active ? 600 : 400,
              }}
              aria-current={active ? 'page' : undefined}
            >
              {t.label}
            </button>
          );
        })}
      </div>

      {loading ? (
        <div className="py-12 text-center text-xs" style={{ color: 'var(--text-muted)' }}>加载中...</div>
      ) : (
        <>
          {tab === 'summary' && summary && (
            <div className="space-y-4">
              {/* 概览卡片 */}
              <div className="grid grid-cols-3 gap-3">
                <SummaryCard label="今日新增" value={summary.new_today} color="var(--color-bid, #d69e2e)" />
                <SummaryCard label="开放中" value={summary.total_open} color="var(--accent)" />
                <SummaryCard label="总计" value={summary.total_all} color="var(--text-primary)" />
              </div>

              {/* 地区分布 */}
              <div className="p-4 rounded-[var(--radius-md)]" style={{ backgroundColor: 'var(--bg-elevated)', border: '1px solid var(--border-color)' }}>
                <h3 className="text-xs font-bold tracking-[0.12em] uppercase mb-3" style={{ color: 'var(--text-primary)' }}>
                  地区分布
                </h3>
                <div className="space-y-1.5">
                  {Object.entries(summary.region_distribution)
                    .sort((a, b) => b[1] - a[1])
                    .slice(0, 15)
                    .map(([region, count]) => {
                      const maxCount = Math.max(...Object.values(summary.region_distribution));
                      const pct = maxCount > 0 ? (count / maxCount) * 100 : 0;
                      return (
                        <div key={region} className="flex items-center gap-2">
                          <span className="text-[11px] w-20 truncate shrink-0" style={{ color: 'var(--text-primary)' }}>{region}</span>
                          <div className="flex-1 h-2 rounded-sm" style={{ backgroundColor: 'var(--bg-hover)' }}>
                            <div className="h-full rounded-sm transition-all" style={{ width: `${pct}%`, backgroundColor: 'var(--accent)', opacity: 0.7 }} />
                          </div>
                          <span className="text-[10px] font-mono w-8 text-right" style={{ color: 'var(--text-muted)' }}>{count}</span>
                        </div>
                      );
                    })}
                </div>
              </div>

              {/* 状态分布 */}
              <div className="p-4 rounded-[var(--radius-md)]" style={{ backgroundColor: 'var(--bg-elevated)', border: '1px solid var(--border-color)' }}>
                <h3 className="text-xs font-bold tracking-[0.12em] uppercase mb-3" style={{ color: 'var(--text-primary)' }}>
                  状态分布
                </h3>
                <div className="flex flex-wrap gap-2">
                  {Object.entries(summary.status_distribution)
                    .sort((a, b) => b[1] - a[1])
                    .map(([status, count]) => (
                      <span key={status} className="text-[11px] px-2 py-1 rounded-sm" style={{ backgroundColor: 'var(--bg-hover)', color: 'var(--text-secondary)' }}>
                        {status}: <strong className="font-mono">{count}</strong>
                      </span>
                    ))}
                </div>
              </div>
            </div>
          )}

          {tab === 'competitors' && competitors && (
            <div className="space-y-4">
              <p className="text-xs" style={{ color: 'var(--text-muted)' }}>
                基于 {competitors.total_items} 条标讯标题的热词分析
              </p>

              {/* 竞品热词词云 */}
              <div className="p-4 rounded-[var(--radius-md)]" style={{ backgroundColor: 'var(--bg-elevated)', border: '1px solid var(--border-color)' }}>
                <h3 className="text-xs font-bold tracking-[0.12em] uppercase mb-3" style={{ color: 'var(--text-primary)' }}>
                  高频关键词
                </h3>
                <div className="flex flex-wrap gap-1.5">
                  {competitors.top_keywords.map((kw, i) => {
                    const maxCount = competitors.top_keywords[0]?.count || 1;
                    const size = 0.7 + (kw.count / maxCount) * 0.8;
                    const opacity = 0.5 + (kw.count / maxCount) * 0.5;
                    return (
                      <span
                        key={kw.keyword}
                        className="inline-block transition-colors"
                        style={{
                          fontSize: `${size}rem`,
                          opacity,
                          color: 'var(--text-primary)',
                          padding: '1px 4px',
                          backgroundColor: i % 2 === 0 ? 'var(--bg-hover)' : 'transparent',
                          borderRadius: 'var(--radius-sm)',
                        }}
                        title={`出现 ${kw.count} 次`}
                      >
                        {kw.keyword}
                        <span className="text-[10px] font-mono ml-1" style={{ color: 'var(--text-muted)' }}>{kw.count}</span>
                      </span>
                    );
                  })}
                </div>
              </div>

              {/* 竞品热词表格 */}
              <div className="p-4 rounded-[var(--radius-md)]" style={{ backgroundColor: 'var(--bg-elevated)', border: '1px solid var(--border-color)' }}>
                <h3 className="text-xs font-bold tracking-[0.12em] uppercase mb-3" style={{ color: 'var(--text-primary)' }}>
                  热词排名
                </h3>
                <div className="space-y-1">
                  {competitors.top_keywords.map((kw, i) => {
                    const maxCount = competitors.top_keywords[0]?.count || 1;
                    const pct = (kw.count / maxCount) * 100;
                    return (
                      <div key={kw.keyword} className="flex items-center gap-2 py-1">
                        <span className="text-[10px] font-mono w-5 text-right" style={{ color: 'var(--text-muted)' }}>{i + 1}</span>
                        <span className="text-[11px] w-28 truncate" style={{ color: 'var(--text-primary)' }}>{kw.keyword}</span>
                        <div className="flex-1 h-2 rounded-sm" style={{ backgroundColor: 'var(--bg-hover)' }}>
                          <div className="h-full rounded-sm transition-all" style={{ width: `${pct}%`, backgroundColor: 'var(--color-bid, #d69e2e)' }} />
                        </div>
                        <span className="text-[10px] font-mono w-8 text-right" style={{ color: 'var(--text-muted)' }}>{kw.count}</span>
                      </div>
                    );
                  })}
                </div>
              </div>
            </div>
          )}

          {tab === 'recent' && (
            <div className="space-y-1">
              {recent.length === 0 ? (
                <div className="py-12 text-center text-xs" style={{ color: 'var(--text-muted)' }}>暂无标讯数据</div>
              ) : (
                recent.map(item => (
                  <div
                    key={item.id}
                    className="flex items-center gap-3 px-3 py-2 rounded-[var(--radius-sm)] transition-colors hover:bg-[var(--bg-hover)]"
                    style={{ borderBottom: '1px solid var(--border-color)' }}
                  >
                    <div className="min-w-0 flex-1">
                      <a
                        href={item.url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="text-[11.5px] hover:underline block truncate"
                        style={{ color: 'var(--text-primary)' }}
                      >
                        {item.title}
                      </a>
                      <div className="flex items-center gap-2 mt-0.5">
                        {item.region && (
                          <span className="text-[10px] px-1 py-0.5 rounded-sm" style={{ backgroundColor: 'var(--bg-hover)', color: 'var(--text-muted)' }}>
                            {item.region}
                          </span>
                        )}
                        {item.bid_status && (
                          <span className="text-[10px]" style={{ color: 'var(--text-muted)' }}>{item.bid_status}</span>
                        )}
                        {item.source && (
                          <span className="text-[10px]" style={{ color: 'var(--text-muted)' }}>{item.source}</span>
                        )}
                      </div>
                    </div>
                  </div>
                ))
              )}
            </div>
          )}
        </>
      )}
    </div>
  );
}

/* ─── 子组件 ─── */

function SummaryCard({ label, value, color }: { label: string; value: number; color: string }) {
  return (
    <div
      className="p-4 rounded-[var(--radius-md)] text-center"
      style={{ backgroundColor: 'var(--bg-elevated)', border: '1px solid var(--border-color)' }}
    >
      <div className="text-[10px] font-bold" style={{ color: 'var(--text-muted)' }}>{label}</div>
      <div className="text-2xl font-bold font-mono tabular-nums mt-1" style={{ color }}>
        {value}
      </div>
    </div>
  );
}