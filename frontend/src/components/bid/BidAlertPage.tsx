/**
 * BidAlertPage — 标书提醒与竞品分析 (找回丢失前端入口 Phase 4)
 *
 * 标书摘要 (今日新增/开放数/状态地区分布) + 竞品热词 + 最近标讯。
 * 数据源: GET /api/bid-alert/summary · /competitors · /recent
 */
import { useCallback, useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Icon } from '../Icon';

interface BidSummary {
  new_today: number;
  total_open: number;
  total_all: number;
  region_distribution: Record<string, number>;
  status_distribution: Record<string, number>;
  summary_date: string;
}

interface Competitors {
  total_items: number;
  top_keywords: Array<{ keyword: string; count: number }>;
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

export function BidAlertPage({ onBack }: { onBack?: () => void }) {
  const navigate = useNavigate();
  const goBack = onBack ?? (() => navigate('/'));

  const [summary, setSummary] = useState<BidSummary | null>(null);
  const [competitors, setCompetitors] = useState<Competitors | null>(null);
  const [recent, setRecent] = useState<RecentBid[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [sRes, cRes, rRes] = await Promise.all([
        fetch('/api/bid-alert/summary'),
        fetch('/api/bid-alert/competitors'),
        fetch('/api/bid-alert/recent?limit=20'),
      ]);
      if (!sRes.ok && !cRes.ok && !rRes.ok) {
        setError(`标讯数据加载失败 (${sRes.status})`);
        return;
      }
      if (sRes.ok) setSummary(await sRes.json());
      if (cRes.ok) setCompetitors(await cRes.json());
      if (rRes.ok) {
        const d = await rRes.json();
        setRecent(d.items ?? []);
      }
    } catch {
      setError('标讯数据加载失败: 网络或后端不可达');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const topRegion = Object.entries(summary?.region_distribution ?? {})
    .sort((a, b) => b[1] - a[1]).slice(0, 6);

  return (
    <div className="space-y-4 max-w-5xl">
      {/* 页头 */}
      <div className="flex items-center justify-between pb-2 mb-1" style={{ borderBottom: '2px solid var(--text-primary)' }}>
        <h1 className="text-sm font-bold tracking-wide" style={{ color: 'var(--text-primary)' }}>
          <span className="font-mono mr-2">BID</span>标书提醒与竞品分析
        </h1>
        <div className="flex items-center gap-2">
          <button onClick={load} disabled={loading} className="btn-ghost gap-1.5 px-2 py-1 text-[10px]">
            {loading ? '刷新中...' : '刷新'}
          </button>
          <button onClick={goBack} className="btn-ghost gap-1.5 px-2 py-1 text-[10px]" aria-label="返回首页">
            <Icon size={11}>
              <line x1="19" y1="12" x2="5" y2="12" />
              <polyline points="12 19 5 12 12 5" />
            </Icon>
            <span className="hidden sm:inline">返回首页</span>
          </button>
        </div>
      </div>

      {error && (
        <div className="p-3 rounded-[var(--radius-sm)] text-xs font-mono"
          style={{ color: 'var(--color-error)', border: '1px solid var(--color-error)' }}>
          {error}
        </div>
      )}

      {loading && !summary && (
        <div className="text-sm py-12 text-center" style={{ color: 'var(--text-muted)' }}>加载中...</div>
      )}

      {summary && (
        <>
          {/* 摘要三卡 */}
          <div className="grid grid-cols-3 gap-2">
            <div className="p-3 rounded-[var(--radius-sm)] text-center" style={{ border: '1px solid var(--border-color)', backgroundColor: 'var(--bg-elevated)' }}>
              <div className="text-xl font-mono font-bold" style={{ color: 'var(--accent)' }}>{summary.new_today}</div>
              <div className="text-[10px]" style={{ color: 'var(--text-muted)' }}>今日新增</div>
            </div>
            <div className="p-3 rounded-[var(--radius-sm)] text-center" style={{ border: '1px solid var(--border-color)', backgroundColor: 'var(--bg-elevated)' }}>
              <div className="text-xl font-mono font-bold" style={{ color: 'var(--color-success)' }}>{summary.total_open}</div>
              <div className="text-[10px]" style={{ color: 'var(--text-muted)' }}>开放中</div>
            </div>
            <div className="p-3 rounded-[var(--radius-sm)] text-center" style={{ border: '1px solid var(--border-color)', backgroundColor: 'var(--bg-elevated)' }}>
              <div className="text-xl font-mono font-bold" style={{ color: 'var(--text-primary)' }}>{summary.total_all}</div>
              <div className="text-[10px]" style={{ color: 'var(--text-muted)' }}>标讯总量</div>
            </div>
          </div>

          {/* 地区分布 */}
          <section className="p-3 rounded-[var(--radius-sm)]" style={{ border: '1px solid var(--border-color)', backgroundColor: 'var(--bg-elevated)' }}>
            <h3 className="text-xs font-mono font-semibold mb-2" style={{ color: 'var(--text-primary)' }}>地区分布 Top 6</h3>
            {topRegion.length === 0 ? (
              <p className="text-[10px]" style={{ color: 'var(--text-muted)' }}>暂无数据</p>
            ) : (
              <div className="flex flex-wrap gap-1.5">
                {topRegion.map(([region, count]) => (
                  <span key={region} className="text-[10px] font-mono px-1.5 py-0.5 rounded"
                    style={{ backgroundColor: 'var(--bg-hover)', color: 'var(--text-secondary)', border: '1px solid var(--border-color)' }}>
                    {region} · {count}
                  </span>
                ))}
              </div>
            )}
          </section>

          {/* 竞品热词 */}
          {competitors && (
            <section className="p-3 rounded-[var(--radius-sm)]" style={{ border: '1px solid var(--border-color)', backgroundColor: 'var(--bg-elevated)' }}>
              <h3 className="text-xs font-mono font-semibold mb-2" style={{ color: 'var(--text-primary)' }}>
                竞品热词 · 样本 {competitors.total_items} 条
              </h3>
              {competitors.top_keywords.length === 0 ? (
                <p className="text-[10px]" style={{ color: 'var(--text-muted)' }}>样本不足, 暂无热词</p>
              ) : (
                <div className="space-y-1.5">
                  {competitors.top_keywords.map(({ keyword, count }) => {
                    const max = competitors.top_keywords[0]?.count || 1;
                    return (
                      <div key={keyword} className="flex items-center gap-2">
                        <span className="text-[11px] font-mono w-28 truncate" style={{ color: 'var(--text-secondary)' }}>{keyword}</span>
                        <div className="flex-1 h-1.5 rounded" style={{ backgroundColor: 'var(--bg-hover)' }}>
                          <div className="h-1.5 rounded" style={{ width: `${Math.max(6, (count / max) * 100)}%`, backgroundColor: 'var(--accent)' }} />
                        </div>
                        <span className="text-[10px] font-mono tabular-nums w-8 text-right" style={{ color: 'var(--text-muted)' }}>{count}</span>
                      </div>
                    );
                  })}
                </div>
              )}
            </section>
          )}

          {/* 最近标讯 */}
          <section className="p-3 rounded-[var(--radius-sm)]" style={{ border: '1px solid var(--border-color)', backgroundColor: 'var(--bg-elevated)' }}>
            <h3 className="text-xs font-mono font-semibold mb-2" style={{ color: 'var(--text-primary)' }}>最近标讯 · {recent.length}</h3>
            {recent.length === 0 ? (
              <p className="text-[10px]" style={{ color: 'var(--text-muted)' }}>暂无标讯, 等待 bid 类采集入库</p>
            ) : (
              <ul className="divide-y" style={{ borderColor: 'var(--border-light)' }}>
                {recent.map(b => (
                  <li key={b.id} className="py-1.5 flex items-center gap-2 text-[11px]">
                    {b.url ? (
                      <a href={b.url} target="_blank" rel="noopener noreferrer"
                        className="flex-1 truncate hover:underline" style={{ color: 'var(--text-primary)' }}>
                        {b.title}
                      </a>
                    ) : (
                      <span className="flex-1 truncate" style={{ color: 'var(--text-primary)' }}>{b.title}</span>
                    )}
                    {b.region && (
                      <span className="text-[10px] font-mono shrink-0" style={{ color: 'var(--text-muted)' }}>{b.region}</span>
                    )}
                    {b.bid_status && (
                      <span className="text-[10px] font-mono px-1 rounded shrink-0"
                        style={{ backgroundColor: 'var(--bg-hover)', color: 'var(--text-secondary)' }}>
                        {b.bid_status}
                      </span>
                    )}
                  </li>
                ))}
              </ul>
            )}
          </section>
        </>
      )}
    </div>
  );
}
