/**
 * SentinelHomePage — 哨兵终端 · 资料层首页 (V2 设计稿 data 屏)
 *
 * 信息架构: 三层工作流的资料层 — 采集与组织。
 * 壳 (appbar + 心跳条) 由 SentinelShell 提供, 本页聚焦:
 *  - 阅读模式四态 (简报/扫描/深度/告警) + 频道 chips
 *  - 头条叙事 + 次级重点 + 快讯流 (+ 可展开高危告警)
 *  - 右栏: 源监控 / 质量门禁 24h / 今日行动
 *
 * 数据源 (全部真实 API):
 *  - GET /api/hotspots?category&time_range=24h&limit=40
 *  - GET /api/quality/summary · GET /api/todos (右栏)
 *  - SSE /api/events (collect 完成后节流刷新)
 */
import { useCallback, useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useSSE } from '../../hooks/useSSE';
import { CATEGORIES, HotspotItem } from '../../types';
import { SentinelShell, usePipe, usePipeReloadOnSse } from './SentinelShell';
import { SentinelRail } from './SentinelRail';
import './sentinel.css';

type ReadMode = 'brief' | 'scan' | 'deep' | 'alert';

interface QualityGateStat {
  pass: number;
  total: number;
  avg_deduction: number;
}
interface QualitySummaryRaw {
  summary?: Record<string, QualityGateStat>;
}

interface TodoRow {
  id: number;
  title: string;
  status: string;
}

/** 频道 chips: 分类 → 哨兵短标签 + 分类色 */
const CHANNEL_DEFS: { id: string; label: string; color: string }[] = [
  { id: 'all', label: '全部', color: 'var(--sn-mint)' },
  { id: 'ai', label: 'AI', color: 'var(--sn-cat-ai)' },
  { id: 'ai_security', label: 'AI 安全', color: 'var(--sn-cat-ai)' },
  { id: 'security', label: '网络安全', color: 'var(--sn-cat-sec)' },
  { id: 'finance', label: '金融科技', color: 'var(--sn-cat-fin)' },
  { id: 'startup', label: '创投', color: 'var(--sn-cat-vc)' },
  { id: 'bid', label: '招投标', color: 'var(--sn-cat-bid)' },
  { id: 'github', label: 'GitHub', color: 'var(--sn-cat-git)' },
  { id: 'tech', label: '技术圈', color: 'var(--sn-cat-tech)' },
];

/** 分类 → tag 颜色 (story-top / 次级 / 快讯标签) */
function tagColorOf(category: string): string {
  switch (category) {
    case 'ai': return 'var(--sn-cat-ai)';
    case 'ai_security': return 'var(--sn-cat-ai)';
    case 'security': return 'var(--sn-cat-sec)';
    case 'finance': return 'var(--sn-cat-fin)';
    case 'startup': return 'var(--sn-cat-vc)';
    case 'bid': return 'var(--sn-cat-bid)';
    case 'github': return 'var(--sn-cat-git)';
    case 'tech': return 'var(--sn-cat-tech)';
    default: return 'var(--sn-cat-ai)';
  }
}

function labelOf(category: string): string {
  return CATEGORIES.find(c => c.id === category)?.label ?? category;
}

function relTime(iso?: string | null): string {
  if (!iso) return '--';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return '--';
  const diff = Date.now() - d.getTime();
  const m = Math.floor(diff / 60000);
  if (m < 1) return '刚刚';
  if (m < 60) return `${m} 分钟前`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h} 小时前`;
  const day = Math.floor(h / 24);
  if (day === 1) return '昨天';
  if (day < 7) return `${day} 天前`;
  return d.toLocaleDateString('zh-CN');
}

function heatOf(item: HotspotItem): number {
  const s = item.score ?? item.quality_score ?? 0;
  return Math.max(0, Math.min(5, Math.round(s / 20)));
}

function heatCells(n: number): boolean[] {
  return [1, 2, 3, 4, 5].map(i => i <= n);
}

/** 必须是独立组件: 在 SentinelHomePage 函数体内调用 usePipe 会落在 Provider 之外, 永远读到 null */
function RailWithPipe({ quality, todos }: { quality: QualitySummaryRaw | null; todos: TodoRow[] }) {
  const { pipe } = usePipe();
  return <SentinelRail sources={pipe?.sources ?? []} quality={quality} todos={todos} />;
}

export function SentinelHomePage() {
  const navigate = useNavigate();

  const [mode, setMode] = useState<ReadMode>('brief');
  const [channel, setChannel] = useState('all');

  const [items, setItems] = useState<HotspotItem[]>([]);
  const [total, setTotal] = useState(0);
  const [latestCount, setLatestCount] = useState<number | null>(null);
  const [latestAt, setLatestAt] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [quality, setQuality] = useState<QualitySummaryRaw | null>(null);
  const [todos, setTodos] = useState<TodoRow[]>([]);

  const reloadPipe = usePipeReloadOnSse();

  const loadFeed = useCallback(async (ch: string) => {
    setLoading(true);
    setError(null);
    try {
      // H24 = 上海今日 00:00 起 (与后端 TimeRange 语义一致, "今日收录"口径)
      const params = new URLSearchParams({ category: ch, time_range: '24h', limit: '40' });
      const r = await fetch(`/api/hotspots?${params}`, { headers: { Accept: 'application/json' } });
      if (!r.ok) throw new Error(`请求失败 (${r.status})`);
      const data = await r.json();
      setItems(data.items || []);
      setTotal(data.total || 0);
      setLatestCount(data.latest_ingestion_count ?? null);
      setLatestAt(data.latest_ingestion_at ?? null);
    } catch (e) {
      setError(e instanceof Error ? e.message : '数据加载失败');
    } finally {
      setLoading(false);
    }
  }, []);

  // 右栏数据 (一次性 + SSE 刷新时重拉)
  const loadSide = useCallback(async () => {
    try {
      const [qs, ts] = await Promise.all([
        fetch('/api/quality/summary').then(r => (r.ok ? r.json() : null)).catch(() => null),
        fetch('/api/todos').then(r => (r.ok ? r.json() : { items: [] })).catch(() => ({ items: [] })),
      ]);
      setQuality(qs);
      setTodos(((ts.items || []) as TodoRow[]).filter(i => i.status !== 'done').slice(0, 6));
    } catch { /* 右栏失败不阻塞主列 */ }
  }, []);

  useEffect(() => {
    loadFeed(channel);
  }, [channel, loadFeed]);

  useEffect(() => {
    loadSide();
  }, [loadSide]);

  // SSE: collect 相关事件 → 节流刷新 (10s)
  useSSE({
    onEvent: () => {
      reloadPipe();
      loadFeed(channel);
      loadSide();
    },
  });

  // 告警条目: 快讯池 (头条/次级之后) 中安全类目评分最高的一条
  const alertItem = useMemo(() => {
    const pool = items.slice(3);
    const sec = pool.filter(i => i.category === 'security' || i.category === 'ai_security');
    if (sec.length === 0) return null;
    return [...sec].sort((a, b) => (b.score ?? b.quality_score ?? 0) - (a.score ?? a.quality_score ?? 0))[0];
  }, [items]);

  const [lead, secondaries, flashes] = useMemo(() => {
    const rest = items.filter(i => i.id !== alertItem?.id);
    return [rest[0] ?? null, rest.slice(1, 3), rest.slice(3)];
  }, [items, alertItem]);

  return (
    <SentinelShell layer="data" mode={mode} ingested={total}>
      {/* ===== 阅读模式 & 频道条 ===== */}
      <div className="controlbar">
        <div className="modes" role="group" aria-label="阅读模式">
          {([['brief', '简报'], ['scan', '扫描'], ['deep', '深度']] as const).map(([m, label]) => (
            <button key={m} className="mode-btn" aria-pressed={mode === m} onClick={() => setMode(m)}>{label}</button>
          ))}
          <button className="mode-btn mode-alert-on" aria-pressed={mode === 'alert'} onClick={() => setMode('alert')}>告警</button>
        </div>
        <nav className="channels" aria-label="内容频道">
          {CHANNEL_DEFS.map(ch => (
            <button
              key={ch.id}
              className={`chip${channel === ch.id ? ' active' : ''}`}
              style={{ '--sn-dot': ch.color } as React.CSSProperties}
              onClick={() => setChannel(ch.id)}
            >
              <i aria-hidden="true" />{ch.label}
            </button>
          ))}
        </nav>
      </div>

      {/* ===== 主布局 ===== */}
      <div className="layout">
        <main className="maincol">
          {loading ? (
            <div className="story-top" aria-busy="true">
              <div className="skel-line w1" /><div className="skel-line w2" /><div className="skel-line w3" /><div className="skel-line w2" />
            </div>
          ) : error ? (
            <div className="empty-panel">
              <div className="empty-ring" aria-hidden="true">
                <svg width="20" height="20" viewBox="0 0 20 20" fill="none"><path d="M10 5v5l3 3" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" /><circle cx="10" cy="10" r="7.5" stroke="currentColor" strokeWidth="1.5" /></svg>
              </div>
              <h3>数据加载失败</h3>
              <p>{error} — 请确认后端服务运行在 127.0.0.1:8000。</p>
              <button className="empty-cta" onClick={() => loadFeed(channel)}>重试
                <svg width="14" height="14" viewBox="0 0 14 14" fill="none" aria-hidden="true"><path d="M2.5 7a4.5 4.5 0 1 1 1.3 3.2M2.5 7V4M2.5 7h3" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" /></svg>
              </button>
            </div>
          ) : items.length === 0 ? (
            <div className="empty-panel">
              <div className="empty-ring" aria-hidden="true">
                <svg width="20" height="20" viewBox="0 0 20 20" fill="none"><path d="M10 2.5l2 4.5 4.5.7-3.2 3.2.7 4.8L10 13.6l-4 2.1.7-4.8L3.5 7.7 8 7l2-4.5z" stroke="currentColor" strokeWidth="1.3" strokeLinejoin="round" /></svg>
              </div>
              <h3>今日频道暂无收录</h3>
              <p>采集管线每 5 分钟自动运行一轮，也可手动触发一轮立即补采。</p>
              <button className="empty-cta" onClick={async () => { await fetch('/api/refresh', { method: 'POST' }); loadFeed(channel); loadSide(); reloadPipe(); }}>立即采集
                <svg width="14" height="14" viewBox="0 0 14 14" fill="none" aria-hidden="true"><path d="M2.5 7h8M7.5 3.5L11 7l-3.5 3.5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" /></svg>
              </button>
            </div>
          ) : (
            <>
              {/* 头条 */}
              {lead && (
                <article className="story-top">
                  <div className="meta-row">
                    <span className="tag" style={{ '--sn-tag-c': tagColorOf(lead.category) } as React.CSSProperties}><i aria-hidden="true" />{labelOf(lead.category)}</span>
                    <span className="src">{lead.source}</span>
                    <span className="time num">{relTime(lead.published_at)}</span>
                    <span className="time num">评分 {Math.round(lead.score ?? lead.quality_score ?? 0)}</span>
                  </div>
                  <h1 className="headline">
                    <a href={lead.url} target="_blank" rel="noopener noreferrer">{lead.title}</a>
                  </h1>
                  {lead.summary && <p className="standfirst">{lead.summary}</p>}
                  <div className="head-foot">
                    <div className="heatbox" aria-label={`当前热度 ${heatOf(lead)} / 5`}>
                      <span className="heat-cells" aria-hidden="true">
                        {heatCells(heatOf(lead)).map((on, i) => <b key={i} className={on ? 'on' : undefined} />)}
                      </span>
                      <span className="heat-num">{heatOf(lead)}/5</span>
                    </div>
                    <button className="readmore" onClick={() => navigate(`/deep/hotspot/${lead.id}`)}>
                      进入深度阅读
                      <svg width="14" height="14" viewBox="0 0 14 14" fill="none" aria-hidden="true"><path d="M2.5 7h8M7.5 3.5L11 7l-3.5 3.5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" /></svg>
                    </button>
                  </div>
                </article>
              )}

              {/* 次级重点 */}
              {secondaries.length > 0 && (
                <section className="secondary" aria-label="次级重点">
                  {secondaries.map((item, idx) => (
                    <div className="sub-item" key={item.id}>
                      <span className="sub-index num">{String(idx + 2).padStart(2, '0')}</span>
                      <div className="sub-body">
                        <a href={item.url} target="_blank" rel="noopener noreferrer"><div className="sub-title">{item.title}</div></a>
                        <div className="sub-meta">
                          <span className="src">{item.source}</span>
                          <span className="time num">{relTime(item.published_at)}</span>
                          <span className="mini-heat" aria-hidden="true">
                            {heatCells(heatOf(item)).map((on, i) => <b key={i} className={on ? 'on' : undefined} />)}
                          </span>
                          <span className="ftag" style={{ color: tagColorOf(item.category), background: 'transparent', border: '1px solid var(--sn-line)' }}>{labelOf(item.category)}</span>
                        </div>
                      </div>
                    </div>
                  ))}
                </section>
              )}

              {/* 快讯流 */}
              <section aria-label="实时快讯">
                <div className="flash-head">
                  <h2>实时快讯</h2>
                  <span className="flash-count num">TODAY {items.length} ITEMS{latestCount != null ? ` · 最近一轮 +${latestCount}` : ''}{latestAt ? ` · ${relTime(latestAt)}` : ''}</span>
                </div>
                <ul className="flash-list">
                  {/* 高危告警 (可展开) */}
                  {alertItem && (
                    <li className="flash-item alert-wrap">
                      <div
                        className={`alert-item${mode === 'alert' ? ' open' : ''}`}
                        role="button"
                        tabIndex={0}
                        aria-expanded={mode === 'alert'}
                        onClick={() => setMode(m => (m === 'alert' ? 'brief' : 'alert'))}
                        onKeyDown={e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); setMode(m => (m === 'alert' ? 'brief' : 'alert')); } }}
                      >
                        <div className="alert-bar">
                          <span className="flash-time num">{relTime(alertItem.published_at)}</span>
                          <div className="flash-body">
                            <div className="flash-title">
                              <span className="alert-badge">高危</span>
                              {alertItem.title}
                              <span className="alert-chev" aria-hidden="true" style={{ display: 'inline-flex', verticalAlign: -2, marginLeft: 6 }}>
                                <svg width="11" height="11" viewBox="0 0 11 11" fill="none"><path d="M3.5 2l3.5 3.5L3.5 9" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" /></svg>
                              </span>
                            </div>
                          </div>
                          <div className="flash-side">
                            <span className="flash-src">{alertItem.source}</span>
                            <span className="heat-num">评分 {Math.round(alertItem.score ?? alertItem.quality_score ?? 0)}</span>
                          </div>
                        </div>
                      </div>
                      <div className={`alert-detail${mode === 'alert' ? ' show' : ''}`} onClick={e => e.stopPropagation()}>
                        {alertItem.summary || '详见原文。'}
                        <br />
                        <b>分类：</b>{labelOf(alertItem.category)} · <b>来源：</b>{alertItem.source}
                        <div className="alert-actions">
                          <button className="abtn" onClick={() => navigate(`/deep/hotspot/${alertItem.id}`)}>进入深读</button>
                          <button className="abtn" onClick={() => window.open(alertItem.url, '_blank', 'noopener')}>查看原文</button>
                        </div>
                      </div>
                    </li>
                  )}

                  {/* 常规快讯 */}
                  {flashes.map(item => (
                    <li className="flash-item" key={item.id}>
                      <span className="flash-time num">{relTime(item.published_at)}</span>
                      <div className="flash-body">
                        <a href={item.url} target="_blank" rel="noopener noreferrer"><span className="flash-title">{item.title}</span></a>
                        <span className="flash-tags"><span className="ftag" style={{ color: tagColorOf(item.category) }}>{labelOf(item.category)}</span></span>
                      </div>
                      <div className="flash-side">
                        <span className="flash-src">{item.source}</span>
                        <span className="mini-heat" aria-hidden="true">
                          {heatCells(heatOf(item)).map((on, i) => <b key={i} className={on ? 'on' : undefined} />)}
                        </span>
                      </div>
                    </li>
                  ))}
                </ul>
              </section>
            </>
          )}
        </main>

        {/* 右栏 */}
        <aside className="rail">
          <RailWithPipe quality={quality} todos={todos} />
        </aside>
      </div>

      {/* 页脚状态行 */}
      <footer className="endnote">
        <span>SECNEWS SENTINEL TERMINAL · 资料层</span>
        <span>本地运行 · 无云端依赖</span>
        <span>SSE 已连接 · 每 5 分钟自动采集</span>
        <span>{total} 篇今日收录</span>
      </footer>
    </SentinelShell>
  );
}
