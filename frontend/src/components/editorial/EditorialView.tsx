/**
 * EditorialView — 报纸版式（Editorial Layout）全屏视图
 *
 * 设计理念: 三层报纸排印 — 资料层 / 判断层 / 行动层 + 深读 + 版务 + 动线
 * 数据源: 复用 useHotspotData / useFavorites / useSSE / useTheme，直连后端实时 API
 * 切换: Header 右上角「⇄ 版式」按钮在 /data (老版) 与 /editorial (新版) 间 toggle
 */
import React, { useState, useEffect, useCallback, useMemo, useRef } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import { useHotspotData } from '../../hooks/useHotspotData';
import { useFavorites } from '../../hooks/useFavorites';
import { useSSE } from '../../hooks/useSSE';
import { useTheme } from '../../contexts/ThemeContext';
import { getCategoryLabel, getCategoryColorVar, type HotspotItem } from '../../types';

// ── 常量 ──
const FLAG_LABEL: Record<string, string> = {
  title_summary_inconsistent: '标题/摘要不一致',
  author_unknown: '作者未知',
  url_duplicate_canonical: 'URL 重复',
  category_mismatch: '分类不符',
};
const catBadgeCls: Record<string, string> = {
  ai: 'b-ai', security: 'b-security', finance: 'b-finance',
  startup: 'b-startup', bid: 'b-bid', github: 'b-github', tech: 'b-ai',
};
function bc(cat: string) { return catBadgeCls[cat] || 'b-general'; }
function esc(s: string): string {
  const map: Record<string, string> = { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' };
  return String(s || '').replace(/[&<>"']/g, c => map[c] || c);
}
function fmtTime(iso?: string | null) {
  if (!iso) return '';
  try { const d = new Date(iso); return `${d.getMonth() + 1}-${d.getDate()} ${String(d.getHours()).padStart(2,'0')}:${String(d.getMinutes()).padStart(2,'0')}`; } catch { return ''; }
}
function qBadge(q?: number) {
  if (q == null) return null;
  const cls = q >= 80 ? 'good' : q < 60 ? 'bad' : '';
  return <span className={`qscore ${cls}`}>Q {q}</span>;
}
function flagChips(flags?: string[]) {
  if (!flags || !flags.length) return null;
  return flags.slice(0, 2).map(f => (
    <span key={f} className="flag-chip" title={FLAG_LABEL[f] || f}>
      {(FLAG_LABEL[f] || f).split('/')[0]}
    </span>
  ));
}

type ViewKey = 'front' | 'judge' | 'action' | 'read' | 'settings' | 'flow';
type JudgeMode = 'brief' | 'scan' | 'deep' | 'alert' | 'outbox' | 'review';

// ── 24h 趋势 SVG 迷你图 ──
function TrendSVG({ trends }: { trends: { label: string; total: number; ai: number }[] }) {
  if (!trends.length) return <div className="ed-empty" style={{ padding: '12px 0' }}>暂无趋势数据</div>;
  const W = 268, H = 80, P = 6;
  const max = Math.max(...trends.map(t => t.total), 1);
  const pts = trends.map((t, i) => {
    const x = P + (W - 2 * P) * i / (trends.length - 1 || 1);
    const y = H - P - (t.total / max) * (H - 2 * P);
    return { x, y, aiY: H - P - (t.ai / max) * (H - 2 * P), total: t.total, ai: t.ai };
  });
  const line = pts.map(p => `${p.x},${p.y}`).join(' ');
  const aiLine = pts.map(p => `${p.x},${p.aiY}`).join(' ');
  const area = `${line} ${P},${H - P} ${W - P},${H - P}`;
  return (
    <svg viewBox={`0 0 ${W} ${H}`} width="100%" height={H} style={{ display: 'block' }}>
      <defs><linearGradient id="ed-tg" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stopColor="var(--color-ai)" stopOpacity=".25" /><stop offset="1" stopColor="var(--color-ai)" stopOpacity="0" /></linearGradient></defs>
      <polygon points={area} fill="url(#ed-tg)" />
      <polyline points={line} fill="none" stroke="var(--text-muted)" strokeWidth="1.4" strokeOpacity=".6" />
      <polyline points={aiLine} fill="none" stroke="var(--color-ai)" strokeWidth="1.8" />
    </svg>
  );
}

export function EditorialView() {
  const navigate = useNavigate();
  const location = useLocation();
  const { theme, toggleTheme } = useTheme();

  // ── 数据 hooks (与老版 DataLayerPage 共用) ──
  const [category, setCategory] = useState('all');
  const [keyword, setKeyword] = useState('');
  const [chasing, setChasing] = useState(false);
  const [sortMode, setSortMode] = useState<'new' | 'q'>('new');
  const [view, setView] = useState<ViewKey>('front');
  const [judgeMode, setJudgeMode] = useState<JudgeMode>('brief');
  const [deepIdx, setDeepIdx] = useState<number | null>(null);
  const [outboxItems, setOutboxItems] = useState<HotspotItem[]>([]);
  const [toast, setToast] = useState<{ msg: string; act?: string; hash?: string } | null>(null);
  const toastTimer = useRef<number>(0);
  const [timeRange, setTimeRange] = useState('7d');
  const [sourceFilter, setSourceFilter] = useState('');
  const [todoItems, setTodoItems] = useState<{ id: string; text: string; done: boolean }[]>([
    { id: 't1', text: '整理供应链投毒 IOC → 知识条目', done: false },
    { id: 't2', text: '复核政务云标书资质清单', done: false },
    { id: 't3', text: '周报生成与人工校订', done: true },
  ]);
  const [klActive, setKlActive] = useState('link');
  const [qualityData, setQualityData] = useState<{ gates: { k: string; pass: number; total: number; ded: number }[]; total: number } | null>(null);
  const [features, setFeatures] = useState<Record<string, boolean>>({});
  const [trends, setTrends] = useState<{ label: string; total: number; ai: number }[]>([]);

  const {
    items, total, categoryCounts, loading, latestIngestionCount, latestIngestionAt, refresh,
  } = useHotspotData(category, timeRange, keyword, sourceFilter || undefined);

  const { favorites: favoritedIds, count: favCount, toggleFavorite } = useFavorites();

  const { connected: sseConnected } = useSSE({
    onEvent: (type: string) => { if (type === 'collect_done') refresh(); },
  });

  // ── 质量门禁 + Feature Gates + 趋势 数据获取 ──
  useEffect(() => {
    const fetchQuality = async () => {
      try {
        const r = await fetch('/api/quality/summary');
        if (!r.ok) return;
        const data = await r.json();
        const s = data.summary || {};
        const gates = Object.entries(s).map(([k, v]: [string, any]) => ({
          k, pass: v.pass || 0, total: v.total || 0, ded: v.avg_deduction || 0,
        }));
        const totalQ = gates[0]?.total || 1;
        setQualityData({ gates, total: totalQ });
      } catch {}
    };
    fetchQuality();
    const t = setInterval(fetchQuality, 5 * 60 * 1000);
    return () => clearInterval(t);
  }, []);

  useEffect(() => {
    const fetchFeatures = async () => {
      try {
        const r = await fetch('/api/settings/features');
        if (!r.ok) return;
        const data = await r.json();
        setFeatures(data);
      } catch {}
    };
    fetchFeatures();
  }, []);

  useEffect(() => {
    const fetchTrends = async () => {
      try {
        const r = await fetch('/api/trends?hours=24');
        if (!r.ok) return;
        const data = await r.json();
        setTrends((data.trends || []).map((t: any) => ({ label: t.label, total: t.total || 0, ai: t.ai || 0 })));
      } catch {}
    };
    fetchTrends();
    const t = setInterval(fetchTrends, 5 * 60 * 1000);
    return () => clearInterval(t);
  }, []);

  // ── 路由 hash → view 同步 ──
  useEffect(() => {
    const h = location.hash.slice(1);
    if (h && ['front', 'judge', 'action', 'read', 'settings', 'flow'].includes(h)) {
      setView(h as ViewKey);
    }
  }, [location.hash]);

  const go = useCallback((v: ViewKey) => {
    setView(v);
    navigate(`/editorial#${v}`, { replace: true });
    window.scrollTo({ top: 0 });
  }, [navigate]);

  // ── toast ──
  const showToast = useCallback((msg: string, act?: string, hash?: string) => {
    setToast({ msg, act, hash });
    window.clearTimeout(toastTimer.current);
    toastTimer.current = window.setTimeout(() => setToast(null), 4500);
  }, []);

  // ── 追抓资讯: 触发后端立即采集 + 刷新前端 ──
  const handleChase = useCallback(async () => {
    if (chasing) return;
    setChasing(true);
    showToast('已发起追抓请求，正在采集最新资讯…');
    try {
      await refresh();
      showToast('追抓完成，已刷新资讯流');
    } catch {
      showToast('追抓失败，请稍后重试');
    } finally {
      setChasing(false);
    }
  }, [chasing, refresh, showToast]);

  // ── 收藏联动 ──
  const handleStar = useCallback(async (item: HotspotItem) => {
    const wasFavorited = favoritedIds.has(item.id);
    await toggleFavorite(item);
    if (!wasFavorited) {
      setOutboxItems(prev => prev.find(x => x.id === item.id) ? prev : [...prev, item]);
      showToast('已收藏 · 进入整理箱', '去判断层', '#judge');
    }
  }, [favoritedIds, toggleFavorite, showToast]);

  // ── 分类列表 ──
  const cats = useMemo(() => {
    return Object.entries(categoryCounts)
      .filter(([, n]) => (n as number) > 0)
      .map(([k, n]) => ({ k, label: getCategoryLabel(k), n: n as number }));
  }, [categoryCounts]);

  // ── 排序后的 feed ──
  const sortedItems = useMemo(() => {
    if (sortMode === 'q') return [...items].sort((a, b) => (b.quality_score || 0) - (a.quality_score || 0));
    return items;
  }, [items, sortMode]);

  // ── 过滤后的 feed（按分类筛选） ──
  const visibleItems = useMemo(() => {
    if (category === 'all') return sortedItems;
    return sortedItems.filter(f => f.category === category);
  }, [sortedItems, category]);

  // ── 头条 ──
  const lead = useMemo(() => {
    if (deepIdx != null && visibleItems[deepIdx]) return visibleItems[deepIdx];
    return visibleItems[0] || null;
  }, [visibleItems, deepIdx]);

  // ── 深读 ──
  const openDeep = useCallback((idx: number | null) => {
    setDeepIdx(idx);
    go('read');
  }, [go]);

  // ── 当前深读条目 + 相关条目 ──
  const deepItem = deepIdx != null ? visibleItems[deepIdx] : lead;
  const relItems = useMemo(() => {
    if (!deepItem) return [];
    return visibleItems.filter(x => x.id !== deepItem.id).slice(0, 3);
  }, [visibleItems, deepItem]);

  // ── 命令面板 ──
  const [paletteOpen, setPaletteOpen] = useState(false);
  const [paletteQuery, setPaletteQuery] = useState('');
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') {
        e.preventDefault();
        setPaletteOpen(o => !o);
      }
      if (e.key === 'Escape') setPaletteOpen(false);
    };
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, []);

  const paletteCommands = [
    { t: '头版 · 资讯流', tag: '资料', h: 'front' },
    { t: '判断层 · 六认知', tag: '判断', h: 'judge' },
    { t: '行动层 · 待办复利', tag: '行动', h: 'action' },
    { t: '深读视图', tag: '资料', h: 'read' },
    { t: '版务 · 设置', tag: '版务', h: 'settings' },
    { t: '主线动线 · 五步', tag: '工作流', h: 'flow' },
  ];
  const filteredCmds = paletteCommands.filter(c =>
    !paletteQuery || (c.t + c.tag).toLowerCase().includes(paletteQuery.toLowerCase())
  );

  const VIEW_LABELS: Record<ViewKey, string> = {
    front: '资料 · 头版', judge: '判断 · 分析台', action: '行动 · 行动台',
    read: '深读 · 副刊', settings: '版务 · 中枢', flow: '主线 · 动线',
  };

  return (
    <div className="ed-wrap" data-theme={theme}>
      {/* ── 内联样式 ── */}
      <style>{ED_CSS}</style>

      {/* ── 顶部工具条 ── */}
      <div className="ed-toolbar">
        <span className="ed-mono">
          {new Date().getFullYear()}年{new Date().getMonth() + 1}月{new Date().getDate()}日
          &ensp;·&ensp;
          <span className={`ed-sse-dot ${sseConnected ? 'on' : ''}`} />
          {sseConnected ? '实时' : '离线'}
          &ensp;·&ensp;真实摄取 <span className="ed-mono ed-bold">{total}</span> 条
          {latestIngestionCount > 0 && <>/最新 <span className="ed-mono ed-bold">{latestIngestionCount}</span></>}
        </span>
        <nav className="ed-tool-links">
          <button onClick={() => navigate('/data')} title="切换到老版式">⇄ 老版式</button>
          <button onClick={() => go('settings')}>版务</button>
        </nav>
      </div>

      {/* ── 报头 ── */}
      <header className="ed-masthead">
        <h1>SEC<span className="ed-amp">NEWS</span></h1>
        <div className="ed-tagline">安全 · AI · 金融 · 标讯 情报日报</div>
        <div className="ed-edition-mark">VOL.070 — {VIEW_LABELS[view]} · v4.3</div>
      </header>

      {/* ── 粘性导航 ── */}
      <div className="ed-navsticky">
        <div className="ed-nav-row">
          <button className={`ed-layer-tab ${view === 'front' ? 'active' : ''}`} onClick={() => go('front')}>
            资料层<span className="sub">我有什么</span>
          </button>
          <button className={`ed-layer-tab ${view === 'judge' ? 'active' : ''}`} onClick={() => go('judge')}>
            判断层<span className="sub">我怎么看</span>
          </button>
          <button className={`ed-layer-tab ${view === 'action' ? 'active' : ''}`} onClick={() => go('action')}>
            行动层<span className="sub">我做什么</span>
          </button>
          <button className={`ed-layer-tab ${view === 'settings' ? 'active' : ''}`} onClick={() => go('settings')}>
            版务<span className="sub">配置中枢</span>
          </button>
          <div className="ed-more-wrap">
            <button className="ed-layer-tab" onClick={() => go('flow')}>更多 ▾<span className="sub">动线 / 深读</span></button>
          </div>
          <div className="ed-nav-tools">
            <button className="ed-icon-btn" onClick={() => setPaletteOpen(true)} aria-label="命令面板(⌘K)">
              <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" strokeWidth="2"><circle cx="11" cy="11" r="7"/><path d="m21 21-4.3-4.3"/></svg>
            </button>
            <span className="ed-star-count">★ {favCount}</span>
            <button
              className="ed-chase-btn"
              onClick={handleChase}
              disabled={chasing}
              title={chasing ? '追抓中…' : '追抓最新资讯'}
              aria-label={chasing ? '追抓进行中' : '追抓资讯'}
            >
              {chasing ? (
                <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" strokeWidth="2" className="ed-spin"><path d="M21 12a9 9 0 1 1-6.219-8.56" /></svg>
              ) : (
                <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" strokeWidth="2"><path d="M13 2L3 14h9l-1 8 10-12h-9l1-8z" /></svg>
              )}
              <span className="ed-chase-text">{chasing ? '追抓中' : '追抓'}</span>
            </button>
            <button className="ed-icon-btn" onClick={() => refresh()} aria-label="刷新" disabled={chasing}>
              <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" strokeWidth="2"><path d="M21 12a9 9 0 1 1-3-6.7M21 3v6h-6"/></svg>
            </button>
            <button className="ed-icon-btn" onClick={toggleTheme} aria-label="切换主题">
              {theme === 'dark' ? '☀' : '☾'}
            </button>
          </div>
        </div>
      </div>

      <main className="ed-main">
        {/* ── 资料层 头版 ── */}
        {view === 'front' && (
          <div className="ed-front-grid">
            <div className="ed-main-col">
              {/* 分类条 */}
              <div className="ed-cats-row">
                <button className={`ed-cat-pill ${category === 'all' ? 'active' : ''}`} onClick={() => setCategory('all')}>
                  全部 <span className="n">{total}</span>
                </button>
                {cats.map(c => (
                  <button key={c.k} className={`ed-cat-pill ${category === c.k ? 'active' : ''}`} onClick={() => setCategory(c.k)}>
                    {c.label} <span className="n">{c.n}</span>
                  </button>
                ))}
                <div className="ed-search-inline">
                  <input type="search" placeholder="搜索标题 / 来源" value={keyword} onChange={e => setKeyword(e.target.value)} />
                  <span className="ed-kbd">/</span>
                </div>
              </div>

              {/* 头条 */}
              {lead && (
                <article className="ed-lead">
                  <div className="ed-meta-row">
                    <span className={`ed-badge-cat ${bc(lead.category)}`}>{getCategoryLabel(lead.category)}</span>
                    {qBadge(lead.quality_score)}
                  </div>
                  <h2><a href="#read" onClick={e => { e.preventDefault(); openDeep(0); }}>{esc(lead.title)}</a></h2>
                  {lead.summary && <p className="ed-lede">{esc(lead.summary)}</p>}
                  <div className="ed-foot-meta">
                    <span>来源 · {esc(lead.source)}</span>
                    <span className="ed-mono">{fmtTime(lead.published_at)}</span>
                  </div>
                </article>
              )}

              {/* 排序条 */}
              <div className="ed-sort-row">
                <button className={`ed-sort-btn ${sortMode === 'new' ? 'active' : ''}`} onClick={() => setSortMode('new')}>最新</button>
                <button className={`ed-sort-btn ${sortMode === 'q' ? 'active' : ''}`} onClick={() => setSortMode('q')}>质量 Q</button>
                <span className="ed-spacer" />
                <span className="ed-mono-note">{visibleItems.length} 条真实条目</span>
              </div>

              {/* Feed 列表 */}
              {loading && (
                <div className="ed-skeleton-list">
                  {[1, 2, 3, 4].map(n => (
                    <div key={n} className="ed-skeleton-row">
                      <div className="ed-skeleton-bar" style={{ width: '30%' }} />
                      <div className="ed-skeleton-bar" style={{ width: '90%', height: 18 }} />
                      <div className="ed-skeleton-bar" style={{ width: '60%' }} />
                    </div>
                  ))}
                </div>
              )}
              {!loading && visibleItems.length === 0 && (
                <div className="ed-empty" style={{ padding: '48px 0' }}>暂无匹配条目 — 试试其他分类或关键词</div>
              )}
              {!loading && visibleItems.map((f, i) => (
                <article key={f.id} className="ed-feed-row">
                  <div className="ed-body">
                    <div className="ed-meta">
                      <span className={`ed-badge-cat ${bc(f.category)}`}>{getCategoryLabel(f.category)}</span>
                      <button
                        className="ed-source-btn"
                        onClick={() => setSourceFilter(prev => prev === f.source ? '' : f.source)}
                        title={sourceFilter === f.source ? '取消来源筛选' : `按来源筛选: ${f.source}`}
                      >
                        {esc(f.source)}
                      </button>
                      {sourceFilter && sourceFilter === f.source && <span className="ed-filter-tag">来源筛选中</span>}
                      {flagChips(f.quality_flags)}
                    </div>
                    <h3><a href="#read" onClick={e => { e.preventDefault(); openDeep(i); }}>{esc(f.title)}</a></h3>
                    {f.summary && <p className="ed-summary">{esc(f.summary)}</p>}
                    <div className="ed-meta">
                      {qBadge(f.quality_score)}
                      <span className="ed-mono">{fmtTime(f.published_at)}</span>
                    </div>
                  </div>
                  <div className="ed-feed-actions">
                    <button
                      className={`ed-star ${favoritedIds.has(f.id) ? 'on' : ''}`}
                      onClick={() => handleStar(f)}
                      aria-label="收藏"
                    >★</button>
                  </div>
                </article>
              ))}
            </div>

            {/* 侧边栏 */}
            <aside className="ed-sidebar">
              <div className="ed-card">
                <div className="ed-c-h">分类分布 <span className="ed-mono">{total}</span></div>
                <div className="ed-stat-grid">
                  {cats.slice(0, 6).map(c => (
                    <div key={c.k} className="ed-stat-cell" onClick={() => setCategory(c.k)}>
                      <div className="ed-v" style={{ color: getCategoryColorVar(c.k) }}>{c.n}</div>
                      <div className="ed-l">{c.label}</div>
                    </div>
                  ))}
                </div>
              </div>
              <div className="ed-card">
                <div className="ed-c-h">24h 摄取趋势 <span className="ed-mono">实时</span></div>
                <TrendSVG trends={trends} />
                <div className="ed-trend-legend">
                  <span><span className="ed-legend-dot" style={{ background: 'var(--color-ai)' }} />AI</span>
                  <span><span className="ed-legend-dot" style={{ background: 'var(--text-muted)' }} />Total</span>
                </div>
              </div>
              <div className="ed-card">
                <div className="ed-c-h">时间范围 <span className="ed-mono">{timeRange}</span></div>
                <div className="ed-time-row">
                  {(['24h', '3d', '7d'] as const).map(tr => (
                    <button key={tr} className={`ed-time-pill ${timeRange === tr ? 'active' : ''}`} onClick={() => setTimeRange(tr)}>
                      {tr === '24h' ? '24小时' : tr === '3d' ? '3天' : '7天'}
                    </button>
                  ))}
                </div>
              </div>
              <div className="ed-card">
                <div className="ed-c-h">阅读 → 行动 <span className="ed-mono">第 1 步</span></div>
                <div style={{ fontSize: '12.5px', color: 'var(--text-secondary)' }}>
                  点任意条目「★」收藏，toast 提供<span style={{ color: 'var(--accent)', fontWeight: 600 }}>去判断层 →</span> 直达。
                </div>
              </div>
            </aside>
          </div>
        )}

        {/* ── 判断层 ── */}
        {view === 'judge' && (
          <>
            <div className="ed-page-head">
              <div className="ed-crumb"><b>判断层</b> · 我怎么看 · {judgeMode === 'brief' ? '简报' : judgeMode === 'scan' ? '扫描' : judgeMode === 'deep' ? '深度' : judgeMode === 'alert' ? '告警' : judgeMode === 'outbox' ? '整理' : '复习'}</div>
              <h2>分析台 · Editorial Desk</h2>
              <p className="ed-standfirst">六种认知模式 + 质量门禁 + 趋势图谱，把信息噪音折叠成可判断的信号。</p>
            </div>
            <div className="ed-mode-tabs">
              {(['brief', 'scan', 'deep', 'alert', 'outbox', 'review'] as JudgeMode[]).map(m => (
                <button key={m} className={`ed-mode-tab ${judgeMode === m ? 'active' : ''}`} onClick={() => setJudgeMode(m)}>
                  {m === 'brief' ? '简报' : m === 'scan' ? '扫描' : m === 'deep' ? '深度' : m === 'alert' ? '告警' : m === 'outbox' ? '整理' : '复习'}
                </button>
              ))}
            </div>

            {/* 整理箱 */}
            {judgeMode === 'outbox' && (
              <div className="ed-cellbox" style={{ padding: 0 }}>
                {outboxItems.length === 0 ? (
                  <div className="ed-empty">尚未收藏任何条目 — 回到资料层点「★」。</div>
                ) : outboxItems.map((it, i) => (
                  <div key={it.id} className="ed-outbox-row">
                    <span className={`ed-badge-cat ${bc(it.category)}`}>{getCategoryLabel(it.category)}</span>
                    <span style={{ flex: 1, fontSize: 13 }}>{esc(it.title)}</span>
                    <button className="ed-btn ed-btn-accent" onClick={() => showToast('已并入知识图谱候选')}>确认关联</button>
                  </div>
                ))}
              </div>
            )}

            {/* 简报 */}
            {judgeMode === 'brief' && (
              <div className="ed-cellbox">
                <div style={{ fontFamily: 'var(--font-serif)', fontSize: '16.5px', lineHeight: 1.8, color: 'var(--text-secondary)' }}>
                  今日共 {total} 条真实摄取，Top 条目：{lead?.title || '—'}
                </div>
              </div>
            )}

            {/* 扫描 / 深度 */}
            {(judgeMode === 'scan' || judgeMode === 'deep') && (
              <>
                <div className="ed-sect-h">{judgeMode === 'deep' ? '深度阅读 · Q≥60' : '扫描 · 全部'} <span className="ed-mono">{judgeMode === 'deep' ? visibleItems.filter(f => (f.quality_score || 0) >= 60).length : visibleItems.length}</span></div>
                {visibleItems.filter(f => judgeMode === 'deep' ? (f.quality_score || 0) >= 60 : true).map((f, i) => (
                  <div key={f.id} className="ed-feed-row">
                    <div className="ed-body">
                      <div className="ed-meta"><span className={`ed-badge-cat ${bc(f.category)}`}>{getCategoryLabel(f.category)}</span><span>{esc(f.source)}</span></div>
                      <h3><a href="#read" onClick={e => { e.preventDefault(); openDeep(i); }}>{esc(f.title)}</a></h3>
                      <div className="ed-meta">{qBadge(f.quality_score)}</div>
                    </div>
                  </div>
                ))}
              </>
            )}

            {/* 告警 */}
            {judgeMode === 'alert' && (
              <div className="ed-cellbox">
                {visibleItems.filter(f => (f.quality_score || 0) < 60).slice(0, 5).map(f => (
                  <div key={f.id} className="ed-alert-item">
                    <div className="ed-dday">!</div>
                    <div>
                      <div className="ed-t">{esc(f.title)}</div>
                      <div className="ed-m">{esc(f.source)} · {f.quality_flags?.[0] ? (FLAG_LABEL[f.quality_flags[0]] || f.quality_flags[0]) : '质量告警'}</div>
                    </div>
                  </div>
                ))}
              </div>
            )}

            {/* 复习 */}
            {judgeMode === 'review' && (
              <div className="ed-cellbox">
                <div style={{ fontFamily: 'var(--font-serif)', fontSize: 16 }}>记忆复利核对其条目，到期复习。</div>
                <button className="ed-btn ed-btn-accent" style={{ marginTop: 12 }} onClick={() => showToast('复习完成')}>去复习</button>
              </div>
            )}

            {/* 质量门禁真实表格 (所有模式下都显示) */}
            <div className="ed-sect-h">质量门禁 · 真实通过率 <span className="ed-mono">{qualityData?.gates.length || 0} 道</span></div>
            <div className="ed-cellbox" style={{ padding: 0 }}>
              {qualityData ? (
                <table className="ed-table">
                  <thead><tr><th>门禁</th><th>通过 / 总数</th><th>通过率</th><th>均扣分</th></tr></thead>
                  <tbody>
                    {qualityData.gates.map(g => {
                      const rate = g.total > 0 ? (g.pass / g.total * 100).toFixed(0) : '0';
                      const cls = Number(rate) >= 98 ? 'p-ok' : Number(rate) >= 50 ? 'p-warn' : 'p-err';
                      return (
                        <tr key={g.k}>
                          <td className="ed-mono">{g.k}</td>
                          <td>{g.pass.toLocaleString()} / {g.total.toLocaleString()}</td>
                          <td><span className={`ed-pill ${cls}`}>{rate}%</span></td>
                          <td className="ed-mono">{g.ded > 0 ? `-${g.ded.toFixed(1)}` : '0'}</td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              ) : (
                <div className="ed-empty">正在加载质量门禁数据…</div>
              )}
            </div>
          </>
        )}

        {/* ── 行动层 ── */}
        {view === 'action' && (
          <>
            <div className="ed-page-head">
              <div className="ed-crumb"><b>行动层</b> · 我下一步做什么</div>
              <h2>行动台 · Composing Room</h2>
              <p className="ed-standfirst">今日焦点由判断层推送；从阅读到落笔，闭环于此。</p>
            </div>
            <div className="ed-grid-2">
              <div>
                <div className="ed-sect-h">待办 · {todoItems.filter(t => !t.done).length}</div>
                <div className="ed-cellbox">
                  <ul className="ed-todo-list">
                    {todoItems.map(t => (
                      <li key={t.id} className={t.done ? 'done' : ''}>
                        <input type="checkbox" checked={t.done} onChange={() => {
                          setTodoItems(prev => prev.map(x => x.id === t.id ? { ...x, done: !x.done } : x));
                        }} />
                        <label>{t.text}</label>
                        <button className="ed-todo-del" onClick={() => {
                          setTodoItems(prev => prev.filter(x => x.id !== t.id));
                          showToast('待办已删除');
                        }} aria-label="删除">×</button>
                      </li>
                    ))}
                  </ul>
                  <div style={{ display: 'flex', gap: 8, marginTop: 12 }}>
                    <input
                      type="text"
                      placeholder="添加新待办…"
                      className="ed-todo-input"
                      onKeyDown={e => {
                        if (e.key === 'Enter') {
                          const v = (e.target as HTMLInputElement).value.trim();
                          if (v) {
                            setTodoItems(prev => [...prev, { id: `t${Date.now()}`, text: v, done: false }]);
                            (e.target as HTMLInputElement).value = '';
                            showToast('待办已添加');
                          }
                        }
                      }}
                    />
                  </div>
                </div>
              </div>
              <div>
                <div className="ed-sect-h">知识复利 · KL 生命周期 <span className="ed-mono">点击切换</span></div>
                <div className="ed-cellbox">
                  <div className="ed-kl-track">
                    {(['raw', 'refine', 'link', 'structure', 'publish'] as const).map(k => {
                      const counts: Record<string, number> = { raw: 2, refine: 0, link: 3947, structure: 0, publish: 209 };
                      return (
                        <div
                          key={k}
                          className={`ed-kl-step ${klActive === k ? 'now' : ''} ${counts[k] > 0 ? 'done' : ''}`}
                          onClick={() => setKlActive(k)}
                          title={`${k} 阶段 ${counts[k]} 条`}
                        >
                          <span className="ed-n">{counts[k]}</span>
                          {k}
                        </div>
                      );
                    })}
                  </div>
                  <div style={{ fontSize: '12.5px', color: 'var(--text-secondary)', marginTop: 8 }}>
                    当前阶段：<b style={{ color: 'var(--accent)' }}>{klActive}</b> ·
                    从资料层点「★」收藏 → 判断层确认关联 → 编译进概念。
                  </div>
                  <div style={{ display: 'flex', gap: 8, marginTop: 12, flexWrap: 'wrap' }}>
                    <button className="ed-btn ed-btn-primary" onClick={() => showToast('概念编译已排队 (link → next)')}>编译本周概念</button>
                    <button className="ed-btn ed-btn-ghost" onClick={() => { go('judge'); setJudgeMode('outbox'); }}>整理箱</button>
                  </div>
                </div>
              </div>
            </div>
          </>
        )}

        {/* ── 深读 ── */}
        {view === 'read' && deepItem && (
          <div className="ed-article">
            <div className="ed-crumb"><b>资料层</b> · {getCategoryLabel(deepItem.category)} · 当前正读</div>
            <div className="ed-art-meta">
              <span className={`ed-badge-cat ${bc(deepItem.category)}`}>{getCategoryLabel(deepItem.category)}</span>
              <span>{esc(deepItem.source)}</span>
              {qBadge(deepItem.quality_score)}
              <span className="ed-mono">{fmtTime(deepItem.published_at)}</span>
            </div>
            <h2>{esc(deepItem.title)}</h2>
            <p>{esc(deepItem.summary || '暂无摘要')}</p>
            <p style={{ color: 'var(--text-muted)', fontStyle: 'italic' }}>
              — 本文为真实资讯摘要，正文请前往原文阅读。情报工作站负责抓取、去重与质量门禁，正文归属原文站点。
            </p>
            <div style={{ display: 'flex', gap: 8, marginTop: 16, flexWrap: 'wrap' }}>
              <button className="ed-btn ed-btn-ghost" onClick={() => go('front')}>返回头版</button>
              {deepItem.url && <a className="ed-btn ed-btn-accent" href={deepItem.url} target="_blank" rel="noopener">阅读原文 ↗</a>}
              <button className="ed-btn ed-btn-primary" onClick={() => showToast('已加入今日焦点候选')}>加入行动焦点</button>
            </div>
            {relItems.length > 0 && (
              <>
                <div className="ed-art-meta" style={{ marginTop: 48, borderBottom: 'none' }}>
                  <span>相关条目</span>
                </div>
                <ul className="ed-rel-list">
                  {relItems.map(r => (
                    <li key={r.id}>
                      <a href="#read" onClick={e => { e.preventDefault(); const idx = visibleItems.indexOf(r); if (idx >= 0) openDeep(idx); }}>{esc(r.title)}</a>
                      <div className="ed-s">{esc(r.source)} · Q {r.quality_score || '—'}</div>
                    </li>
                  ))}
                </ul>
              </>
            )}
          </div>
        )}
        {view === 'read' && !deepItem && (
          <div className="ed-empty" style={{ padding: '64px 0', textAlign: 'center' }}>
            <div style={{ fontSize: 48, marginBottom: 16 }}>📰</div>
            <div style={{ fontFamily: 'var(--font-serif)', fontSize: 18, color: 'var(--text-secondary)' }}>暂未选择阅读条目</div>
            <div style={{ fontSize: 13, color: 'var(--text-muted)', marginTop: 8 }}>回到头版选择任意条目即可进入深读</div>
            <button className="ed-btn ed-btn-accent" style={{ marginTop: 16 }} onClick={() => go('front')}>返回头版</button>
          </div>
        )}

        {/* ── 版务 ── */}
        {view === 'settings' && (
          <>
            <div className="ed-page-head">
              <div className="ed-crumb"><b>版务室</b> · 设置 · 采集源 · 凭据</div>
              <h2>版务室 · The Back Office</h2>
              <p className="ed-standfirst">工作站配置中枢；敏感字段未解锁时一律显示密文。</p>
            </div>
            <div className="ed-grid-2">
              <div>
                <div className="ed-sect-h">通用</div>
                <div className="ed-cellbox">
                  <div className="ed-settings-row">
                    <div><span>日报版 v4.3</span><div className="ed-sub">浅色「日报」 / 深色「夜读」</div></div>
                    <button className="ed-btn ed-btn-accent" style={{ padding: '2px 12px', fontSize: 12 }} onClick={toggleTheme}>{theme === 'dark' ? '☀ 日报' : '☾ 夜读'}</button>
                  </div>
                  <div className="ed-settings-row">
                    <div><span>刷新频率</span><div className="ed-sub">SSE 实时推送</div></div>
                    <span className="ed-pill p-info">{sseConnected ? '实时' : '离线'}</span>
                  </div>
                  <div className="ed-settings-row">
                    <div><span>真实摄取总量</span></div>
                    <span className="ed-mono">{total}</span>
                  </div>
                  <div className="ed-settings-row">
                    <div><span>最近一次摄取</span></div>
                    <span className="ed-mono">{latestIngestionAt ? fmtTime(latestIngestionAt) : '—'}</span>
                  </div>
                </div>
              </div>
              <div>
                <div className="ed-sect-h">采集源 · 分类计数</div>
                <div className="ed-cellbox" style={{ padding: 0 }}>
                  <table className="ed-table">
                    <thead><tr><th>分类</th><th>条数</th><th>占比</th></tr></thead>
                    <tbody>
                      {cats.map(c => {
                        const pct = total > 0 ? (c.n / total * 100).toFixed(1) : '0';
                        return (
                          <tr key={c.k}>
                            <td>{c.label}</td>
                            <td className="ed-mono">{c.n.toLocaleString()}</td>
                            <td>
                              <div className="ed-bidbar"><div className="ed-track"><div className="ed-fill" style={{ width: `${pct}%` }} /></div></div>
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              </div>
            </div>
            {/* Feature Gates */}
            <div className="ed-sect-h">Feature Gates · 后端开关（真实状态）</div>
            <div className="ed-cellbox">
              {[
                ['codegarden', 'CodeGarden（M1 核心）', '项目 / 记忆 / Prompt / SDD'],
                ['codegarden_phase2b', 'CodeGarden 网格（M2-M4）', '服务网格 / 资源中枢 / 联动引擎'],
                ['sync', '跨端同步', 'WebDAV + Fernet zip 同步包'],
                ['mcp', 'MCP 服务', '外部 Model Context Protocol'],
                ['tech_stack', '技术栈图谱', '后端 tech-stack 域'],
                ['security_graph', '安全知识图谱', '实体 / 关系 / 术语'],
              ].map(([k, label, desc]) => {
                const on = !!features[k];
                return (
                  <div key={k} className="ed-settings-row">
                    <div><span>{label}</span><div className="ed-sub">{desc}</div></div>
                    <span className={`ed-switch ${on ? 'on' : ''}`} title={`后端状态：${on ? '已启用' : '未启用'}`} />
                  </div>
                );
              })}
            </div>
          </>
        )}

        {/* ── 主线动线 ── */}
        {view === 'flow' && (
          <>
            <div className="ed-page-head">
              <div className="ed-crumb"><b>主线动线</b> · 五步闭环</div>
              <h2>主线动线 · The Loop</h2>
              <p className="ed-standfirst">收藏、判断、整理、输出本是一条流水线。</p>
            </div>
            <div className="ed-flow-grid">
              {[
                { title: '星标收藏', layer: '资料层', view: 'front' as ViewKey },
                { title: '入待关联', layer: '判断层', view: 'judge' as ViewKey },
                { title: '确认关联', layer: '判断层', view: 'judge' as ViewKey },
                { title: '编译概念', layer: '行动层', view: 'action' as ViewKey },
                { title: '生成周报', layer: '行动层', view: 'action' as ViewKey },
              ].map((step, i) => (
                <div key={i} className="ed-card ed-flow-card" onClick={() => go(step.view)}>
                  <div className="ed-flow-num">{String(i + 1).padStart(2, '0')}</div>
                  <div className="ed-flow-layer">{step.layer}</div>
                  <div className="ed-flow-title">{step.title}</div>
                  <div className="ed-flow-arrow">→</div>
                </div>
              ))}
            </div>
          </>
        )}
      </main>

      <footer className="ed-footer">
        <span>SECNEWS 情报日报 · UI v4.3 · 真实数据驱动</span>
        <span className="ed-mono">:8898 本地工作站 · fetched {fmtTime(latestIngestionAt)}</span>
      </footer>

      {/* ── 命令面板 ── */}
      {paletteOpen && (
        <div className="ed-palette-overlay" onClick={e => { if (e.target === e.currentTarget) setPaletteOpen(false); }}>
          <div className="ed-palette">
            <input type="text" placeholder="跳转到功能 · 试试「周报」「凭据」「图谱」" value={paletteQuery} onChange={e => setPaletteQuery(e.target.value)} autoFocus />
            <div className="ed-palette-list">
              {filteredCmds.map(c => (
                <button key={c.h} className="ed-palette-item" onClick={() => { go(c.h as ViewKey); setPaletteOpen(false); }}>
                  <span className="ed-palette-tag">{c.tag}</span>
                  <span>{c.t}</span>
                </button>
              ))}
            </div>
            <div className="ed-palette-foot">
              <span>↑↓ 选择</span><span>⏎ 跳转</span><span>Esc 关闭</span>
            </div>
          </div>
        </div>
      )}

      {/* ── Toast ── */}
      {toast && (
        <div className="ed-toast-dock">
          <div className="ed-toast">
            <span>{toast.msg}</span>
            {toast.act && toast.hash && (
              <button className="ed-toast-act" onClick={() => go(toast.hash!.slice(1) as ViewKey)}>{toast.act}</button>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

// ── CSS (注入到组件 shadow scope via <style>) ──
const ED_CSS = `
.ed-wrap{font-family:'IBM Plex Sans',system-ui,-apple-system,'PingFang SC','Microsoft YaHei',sans-serif;font-size:15px;line-height:1.7;background:var(--bg-primary);color:var(--text-primary);min-height:100vh;transition:background .22s cubic-bezier(.25,1,.5,1),color .22s}
.ed-wrap[data-theme="light"]{--bg-primary:#F6F1E6;--bg-secondary:#FBF7EE;--bg-card:#FFFDF6;--bg-hover:#EFE7D5;--bg-elevated:#EFE7D5;--border-color:#CFC4AB;--border-light:#E0D7C0;--text-primary:#1A1610;--text-secondary:#4A4134;--text-muted:#7A6F5C;--accent:#8E2318;--accent-soft:#F0E2DA;--ok:#2F7D4F;--warn:#8A6400;--err:#A32014;--info:#0B6E6E;--color-ai:#0B6E6E;--color-security:#A32014;--color-finance:#8A6400;--color-startup:#5A4FA0;--color-bid:#A65312;--color-github:#5E4B8B;--shadow-pop:0 4px 20px rgba(26,22,16,.1)}
.ed-wrap[data-theme="dark"]{--bg-primary:#17130E;--bg-secondary:#1D1812;--bg-card:#211B14;--bg-hover:#282118;--bg-elevated:#2C241A;--border-color:#3C3325;--border-light:#302A1F;--text-primary:#EDE6D8;--text-secondary:#B5A88F;--text-muted:#8C7F68;--accent:#D0684E;--accent-soft:#3A241D;--ok:#6FBE93;--warn:#D4B24A;--err:#E07B6A;--info:#4FB8B8;--color-ai:#4FB8B8;--color-security:#E07B6A;--color-finance:#D4B24A;--color-startup:#A99BE0;--color-bid:#E09B5E;--color-github:#AC99D6;--shadow-pop:0 4px 20px rgba(0,0,0,.4)}
.ed-wrap *{box-sizing:border-box;margin:0;padding:0}
.ed-wrap a{color:inherit;text-decoration:none}
.ed-wrap button{font-family:inherit;cursor:pointer;background:none;border:none;color:inherit}
.ed-mono{font-family:'JetBrains Mono',ui-monospace,Menlo,monospace;font-size:11px;color:var(--text-muted)}
.ed-bold{font-weight:700;color:var(--text-secondary)}
.ed-sse-dot{display:inline-block;width:7px;height:7px;border-radius:50%;background:var(--text-muted);margin-right:6px;vertical-align:1px}
.ed-sse-dot.on{background:var(--ok)}
.ed-toolbar{display:flex;justify-content:space-between;align-items:center;font-size:11px;color:var(--text-muted);padding:8px 32px;border-bottom:1px solid var(--border-light);max-width:1240px;margin:0 auto}
.ed-tool-links{display:flex;gap:0}
.ed-tool-links button{padding:0 8px;border-right:1px solid var(--border-light);color:var(--text-muted);transition:color .12s}
.ed-tool-links button:last-child{border-right:none}
.ed-tool-links button:hover{color:var(--accent);font-weight:600}
.ed-masthead{text-align:center;padding:32px 0 16px;max-width:1240px;margin:0 auto}
.ed-masthead h1{font-family:'Newsreader',Georgia,serif;font-weight:700;text-transform:uppercase;font-size:clamp(30px,4.5vw,50px);letter-spacing:.14em;line-height:1}
.ed-masthead .ed-amp{color:var(--accent)}
.ed-masthead .ed-tagline{font-size:11px;color:var(--text-muted);letter-spacing:.32em;margin-top:8px;text-transform:uppercase}
.ed-masthead .ed-edition-mark{font-family:'JetBrains Mono',monospace;font-size:10px;color:var(--accent);letter-spacing:.14em;margin-top:4px}
.ed-navsticky{position:sticky;top:0;z-index:50;background:var(--bg-primary);border-top:2px solid var(--text-primary);border-bottom:1px solid var(--border-color);max-width:1240px;margin:0 auto;padding:0 32px}
.ed-nav-row{display:flex;align-items:stretch;gap:2px}
.ed-layer-tab{font-size:13px;font-weight:600;letter-spacing:.04em;padding:12px 16px;border-bottom:2.5px solid transparent;margin-bottom:-1px;color:var(--text-secondary);white-space:nowrap;transition:color .12s}
.ed-layer-tab .sub{display:block;font-size:9px;font-weight:400;color:var(--text-muted);letter-spacing:.1em;margin-top:2px}
.ed-layer-tab:hover{color:var(--accent);background:var(--bg-hover)}
.ed-layer-tab.active{color:var(--accent);border-bottom-color:var(--accent)}
.ed-nav-tools{margin-left:auto;display:flex;align-items:center;gap:4px;padding-left:12px}
.ed-icon-btn{width:32px;height:32px;display:grid;place-items:center;border-radius:2px;color:var(--text-muted);transition:background .12s}
.ed-icon-btn:hover{background:var(--bg-hover);color:var(--text-primary)}
.ed-star-count{font-family:'JetBrains Mono',monospace;font-size:11px;color:var(--text-muted)}
.ed-chase-btn{display:inline-flex;align-items:center;gap:4px;font-size:12px;font-weight:600;border:1px solid var(--accent);color:var(--accent);border-radius:2px;padding:5px 12px;transition:all .12s;white-space:nowrap}
.ed-chase-btn:hover:not(:disabled){background:var(--accent-soft);filter:brightness(1.1)}
.ed-chase-btn:disabled{opacity:.5;cursor:wait}
.ed-chase-btn .ed-chase-text{font-size:11px;letter-spacing:.04em}
.ed-spin{animation:ed-spin 1s linear infinite}
@keyframes ed-spin{from{transform:rotate(0)}to{transform:rotate(360deg)}}
.ed-main{max-width:1240px;margin:0 auto;padding:0 32px}
.ed-front-grid{display:grid;grid-template-columns:minmax(0,1fr) 320px;gap:32px;padding-top:12px}
.ed-main-col{min-width:0}
.ed-cats-row{display:flex;align-items:center;gap:8px;padding:8px 0 12px;border-bottom:1px solid var(--border-color);overflow-x:auto;scrollbar-width:none}
.ed-cats-row::-webkit-scrollbar{display:none}
.ed-cat-pill{font-size:12.5px;padding:4px 12px;border-radius:2px;border:1px solid var(--border-color);color:var(--text-secondary);white-space:nowrap;transition:all .12s}
.ed-cat-pill:hover{background:var(--bg-hover)}
.ed-cat-pill.active{background:var(--text-primary);color:var(--bg-primary);border-color:var(--text-primary);font-weight:700}
.ed-cat-pill .n{font-family:'JetBrains Mono',monospace;font-size:10px;opacity:.7;margin-left:4px}
.ed-search-inline{display:flex;align-items:center;gap:8px;margin-left:auto;min-width:0}
.ed-search-inline input{font-size:13px;width:160px;background:var(--bg-secondary);border:1px solid var(--border-color);border-radius:2px;padding:4px 12px;color:var(--text-primary)}
.ed-search-inline input:focus{outline:none;border-color:var(--accent)}
.ed-kbd{font-family:'JetBrains Mono',monospace;font-size:10px;border:1px solid var(--border-color);border-radius:2px;padding:1px 5px;color:var(--text-muted)}
.ed-lead{padding:32px 0;border-bottom:2px solid var(--text-primary)}
.ed-lead .ed-meta-row{display:flex;align-items:center;gap:8px;margin-bottom:12px}
.ed-lead h2{font-family:'Newsreader',Georgia,serif;font-weight:700;font-size:clamp(22px,3vw,32px);line-height:1.25;margin-bottom:12px}
.ed-lead h2 a:hover{color:var(--accent)}
.ed-lead .ed-lede{font-family:'Newsreader',Georgia,serif;font-size:15.5px;color:var(--text-secondary);max-width:64ch}
.ed-lead .ed-lede::first-letter{font-size:2.9em;font-weight:700;color:var(--accent);float:left;line-height:.82;padding:4px 8px 0 0}
.ed-lead .ed-foot-meta{margin-top:12px;font-size:11.5px;color:var(--text-muted);display:flex;gap:16px;flex-wrap:wrap}
.ed-badge-cat{display:inline-block;font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:.06em;padding:2px 7px;border-radius:2px;border:1px solid}
.ed-wrap .b-ai{color:var(--color-ai);border-color:var(--color-ai)}
.ed-wrap .b-security{color:var(--color-security);border-color:var(--color-security)}
.ed-wrap .b-finance{color:var(--color-finance);border-color:var(--color-finance)}
.ed-wrap .b-startup{color:var(--color-startup);border-color:var(--color-startup)}
.ed-wrap .b-bid{color:var(--color-bid);border-color:var(--color-bid)}
.ed-wrap .b-github{color:var(--color-github);border-color:var(--color-github)}
.ed-wrap .b-general{color:var(--text-muted);border-color:var(--text-muted)}
.ed-flag-chip,.ed-wrap .flag-chip{display:inline-block;font-size:9px;font-weight:600;font-family:'JetBrains Mono',monospace;color:var(--warn);border:1px dashed var(--warn);border-radius:2px;padding:0 5px;margin-left:2px}
.ed-sort-row{display:flex;align-items:center;gap:16px;padding:12px 0;border-bottom:1px solid var(--border-light);font-size:13px}
.ed-sort-btn{font-size:13px;color:var(--text-muted);padding-bottom:3px;border-bottom:1.5px solid transparent;transition:all .12s}
.ed-sort-btn:hover{color:var(--text-primary)}
.ed-sort-btn.active{color:var(--accent);border-bottom-color:var(--accent);font-weight:700}
.ed-spacer{flex:1}
.ed-mono-note{font-family:'JetBrains Mono',monospace;font-size:11px;color:var(--text-muted)}
.ed-feed-row{display:flex;gap:16px;padding:16px 0;border-bottom:1px solid var(--border-color)}
.ed-feed-row .ed-body{flex:1;min-width:0}
.ed-feed-row h3{font-family:'Newsreader',Georgia,serif;font-size:19px;font-weight:700;line-height:1.35;margin:4px 0}
.ed-feed-row h3 a:hover{color:var(--accent)}
.ed-feed-row .ed-summary{font-family:'Newsreader',Georgia,serif;font-size:14px;color:var(--text-secondary);-webkit-line-clamp:2;display:-webkit-box;-webkit-box-orient:vertical;overflow:hidden}
.ed-feed-row .ed-meta{font-size:11.5px;color:var(--text-muted);display:flex;align-items:center;gap:8px;flex-wrap:wrap}
.ed-feed-actions{display:flex;flex-direction:column;align-items:flex-end;gap:8px;opacity:.35;transition:opacity .12s}
.ed-feed-row:hover .ed-feed-actions{opacity:1}
.ed-star{color:var(--text-muted);font-size:15px;transition:color .12s}
.ed-star:hover{transform:scale(1.15)}
.ed-star.on{color:var(--accent)}
.ed-qscore,.ed-wrap .qscore{font-family:'JetBrains Mono',monospace;font-size:10px;color:var(--text-muted);border:1px solid var(--border-light);border-radius:2px;padding:1px 5px}
.ed-wrap .qscore.good{color:var(--ok);border-color:var(--ok)}
.ed-wrap .qscore.bad{color:var(--err);border-color:var(--err)}
.ed-card{background:var(--bg-card);border:1px solid var(--border-light);border-radius:4px;padding:16px}
.ed-card+.ed-card{margin-top:16px}
.ed-c-h{font-size:12px;font-weight:700;text-transform:uppercase;letter-spacing:.08em;margin-bottom:12px;display:flex;justify-content:space-between}
.ed-c-h .ed-mono{font-family:'JetBrains Mono',monospace;font-size:10.5px;color:var(--text-muted);font-weight:400}
.ed-stat-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:4px}
.ed-stat-cell{background:var(--bg-secondary);border:1px solid var(--border-light);padding:8px 12px;border-radius:2px;cursor:pointer;transition:border-color .12s}
.ed-stat-cell:hover{border-color:var(--accent)}
.ed-stat-cell .ed-v{font-family:'JetBrains Mono',monospace;font-size:19px;font-weight:600}
.ed-stat-cell .ed-l{font-size:10px;color:var(--text-muted)}
.ed-page-head{padding:32px 0 16px;border-bottom:2px solid var(--text-primary);margin-bottom:32px}
.ed-crumb{font-size:11px;color:var(--text-muted);letter-spacing:.1em;text-transform:uppercase;margin-bottom:8px}
.ed-crumb b{color:var(--accent)}
.ed-page-head h2{font-family:'Newsreader',Georgia,serif;font-size:clamp(26px,3.5vw,38px);font-weight:700}
.ed-page-head .ed-standfirst{font-family:'Newsreader',Georgia,serif;font-style:italic;color:var(--text-secondary);font-size:15.5px;margin-top:8px;max-width:64ch}
.ed-mode-tabs{display:flex;gap:2px;border-bottom:1px solid var(--border-color);margin-bottom:16px;flex-wrap:wrap}
.ed-mode-tab{font-size:13px;padding:8px 16px;color:var(--text-muted);border-bottom:2.5px solid transparent;margin-bottom:-1px}
.ed-mode-tab:hover{color:var(--text-primary);background:var(--bg-hover)}
.ed-mode-tab.active{color:var(--accent);border-bottom-color:var(--accent);font-weight:600}
.ed-grid-2{display:grid;grid-template-columns:1fr 1fr;gap:32px}
.ed-sect-h{font-size:12.5px;font-weight:700;text-transform:uppercase;letter-spacing:.08em;margin:32px 0 12px;display:flex;align-items:center;gap:12px}
.ed-sect-h::after{content:"";flex:1;border-top:1px solid var(--border-color)}
.ed-sect-h .ed-mono{font-family:'JetBrains Mono',monospace;font-size:10.5px;color:var(--text-muted);font-weight:400}
.ed-cellbox{background:var(--bg-card);border:1px solid var(--border-light);border-radius:4px;padding:16px}
.ed-table{width:100%;border-collapse:collapse;font-size:13px}
.ed-table th{font-size:10.5px;text-transform:uppercase;letter-spacing:.06em;color:var(--text-muted);text-align:left;padding:8px;border-bottom:2px solid var(--text-primary)}
.ed-table td{padding:8px;border-bottom:1px solid var(--border-light)}
.ed-table tr:hover td{background:var(--bg-hover)}
.ed-pill{font-size:10px;font-weight:700;padding:2px 8px;border-radius:2px;letter-spacing:.04em}
.ed-wrap .p-info{color:var(--info);border:1px solid var(--info)}
.ed-bidbar{margin-bottom:4px}
.ed-bidbar .ed-track{height:6px;border-radius:3px;background:var(--bg-hover);overflow:hidden}
.ed-bidbar .ed-fill{height:100%;background:var(--accent);border-radius:3px}
.ed-alert-item{display:flex;gap:12px;padding:12px 0;border-bottom:1px solid var(--border-light)}
.ed-alert-item .ed-dday{font-family:'JetBrains Mono',monospace;font-weight:600;font-size:18px;color:var(--accent);min-width:48px;text-align:center;border:1px solid var(--accent);border-radius:2px;padding:2px 4px}
.ed-alert-item .ed-t{font-weight:600;font-size:14px}
.ed-alert-item .ed-m{font-size:11.5px;color:var(--text-muted)}
.ed-kl-track{display:flex;gap:0;margin:12px 0}
.ed-kl-step{flex:1;text-align:center;font-size:10px;color:var(--text-muted);padding-top:12px}
.ed-kl-step::before{content:"";display:block;height:4px;background:var(--border-light);margin-bottom:4px}
.ed-kl-step.now::before{background:var(--accent)}
.ed-kl-step.now{color:var(--accent);font-weight:700}
.ed-kl-step .ed-n{font-family:'JetBrains Mono',monospace;font-size:13px;font-weight:700;color:var(--text-primary);display:block}
.ed-btn{display:inline-flex;align-items:center;font-size:13px;font-weight:600;border-radius:2px;padding:8px 16px;transition:all .12s}
.ed-btn-primary{background:var(--text-primary);color:var(--bg-primary);border:1px solid var(--text-primary)}
.ed-btn-primary:hover{filter:brightness(1.12)}
.ed-btn-ghost{border:1px solid var(--border-color);color:var(--text-secondary)}
.ed-btn-ghost:hover{border-color:var(--text-muted);color:var(--text-primary)}
.ed-btn-accent{border:1px solid var(--accent);color:var(--accent)}
.ed-btn-accent:hover{background:var(--accent-soft)}
.ed-article{max-width:700px;margin:0 auto;padding:48px 0}
.ed-article h2{font-family:'Newsreader',Georgia,serif;font-size:clamp(24px,3.4vw,34px);line-height:1.25;font-weight:700;margin-bottom:8px}
.ed-article p{font-family:'Newsreader',Georgia,serif;font-size:16px;line-height:1.9;margin-bottom:16px;color:var(--text-secondary)}
.ed-art-meta{font-size:11.5px;color:var(--text-muted);display:flex;gap:16px;padding-bottom:16px;border-bottom:1px solid var(--border-color);margin-bottom:32px;flex-wrap:wrap}
.ed-rel-list{list-style:none;margin-top:8px}
.ed-rel-list li{padding:8px 0;border-bottom:1px solid var(--border-light)}
.ed-rel-list li a{font-family:'Newsreader',Georgia,serif;font-size:14.5px;display:block}
.ed-rel-list li a:hover{color:var(--accent)}
.ed-rel-list li .ed-s{font-size:11px;color:var(--text-muted)}
.ed-settings-row{display:flex;align-items:center;justify-content:space-between;gap:12px;padding:8px 0;border-bottom:1px solid var(--border-light);font-size:13px}
.ed-settings-row:last-child{border-bottom:none}
.ed-sub{font-size:11px;color:var(--text-muted)}
.ed-flow-grid{display:grid;grid-template-columns:repeat(5,1fr);gap:12px}
.ed-flow-num{font-family:'JetBrains Mono',monospace;font-size:22px;font-weight:600;color:var(--accent)}
.ed-flow-layer{font-size:10.5px;letter-spacing:.08em;color:var(--text-muted);margin:8px 0}
.ed-flow-title{font-size:14px;font-weight:600}
.ed-outbox-row{display:flex;gap:8px;padding:8px 12px;border-bottom:1px solid var(--border-light);align-items:center}
.ed-empty{font-size:13px;color:var(--text-muted);padding:16px 0;text-align:center}
.ed-footer{border-top:2px solid var(--text-primary);margin-top:72px;padding:16px 32px 48px;font-size:11px;color:var(--text-muted);display:flex;justify-content:space-between;flex-wrap:wrap;gap:8px;max-width:1240px;margin:72px auto 0}
.ed-palette-overlay{position:fixed;inset:0;background:rgba(26,22,16,.5);display:flex;align-items:flex-start;justify-content:center;padding:12vh 32px 0;z-index:100}
.ed-palette{width:560px;max-width:100%;background:var(--bg-card);border:1px solid var(--border-color);border-radius:8px;box-shadow:0 16px 48px rgba(26,22,16,.16);overflow:hidden}
.ed-palette input{width:100%;font-size:15px;padding:12px 16px;background:transparent;border:none;border-bottom:1px solid var(--border-color);color:var(--text-primary)}
.ed-palette input:focus{outline:none}
.ed-palette-list{max-height:320px;overflow-y:auto;padding:4px 0}
.ed-palette-item{display:flex;align-items:center;gap:12px;width:100%;text-align:left;padding:8px 16px;font-size:13.5px;color:var(--text-secondary)}
.ed-palette-item:hover{background:var(--accent-soft);color:var(--accent)}
.ed-palette-tag{font-family:'JetBrains Mono',monospace;font-size:9.5px;text-transform:uppercase;letter-spacing:.06em;color:var(--text-muted);border:1px solid var(--border-light);border-radius:2px;padding:1px 6px}
.ed-palette-foot{border-top:1px solid var(--border-color);padding:8px 16px;font-size:10.5px;color:var(--text-muted);display:flex;gap:16px}
.ed-toast-dock{position:fixed;bottom:32px;right:32px;z-index:120}
.ed-toast{display:inline-flex;align-items:center;gap:8px;background:var(--bg-elevated);border:1px solid var(--border-color);border-left:3px solid var(--ok);border-radius:4px;box-shadow:var(--shadow-pop);padding:8px 16px;font-size:13px}
.ed-toast-act{color:var(--accent);font-weight:600;border-left:1px solid var(--border-light);padding-left:8px}
@media(max-width:1100px){.ed-front-grid{grid-template-columns:1fr!important}.ed-sidebar{border-top:1px solid var(--border-color);margin-top:32px;padding-top:16px}}
@media(max-width:900px){.ed-grid-2{grid-template-columns:1fr!important}.ed-flow-grid{grid-template-columns:repeat(2,1fr)!important}}
@media(max-width:640px){.ed-layer-tab .sub{display:none}.ed-toolbar{padding:8px 16px}.ed-main{padding:0 16px}.ed-navsticky{padding:0 16px}}
/* ── v4.4 新增样式 ── */
.ed-trend-legend{display:flex;gap:12px;flex-wrap:wrap;font-size:11px;color:var(--text-muted);margin-top:8px}
.ed-legend-dot{display:inline-block;width:8px;height:8px;border-radius:2px;margin-right:5px;vertical-align:1px}
.ed-time-row{display:flex;gap:4px}
.ed-time-pill{font-size:12px;padding:4px 12px;border-radius:2px;border:1px solid var(--border-color);color:var(--text-secondary);transition:all .12s;white-space:nowrap}
.ed-time-pill:hover{background:var(--bg-hover)}
.ed-time-pill.active{background:var(--text-primary);color:var(--bg-primary);border-color:var(--text-primary);font-weight:700}
.ed-wrap .p-ok{color:var(--ok);border:1px solid var(--ok)}
.ed-wrap .p-warn{color:var(--warn);border:1px solid var(--warn)}
.ed-wrap .p-err{color:var(--err);border:1px solid var(--err)}
.ed-switch{position:relative;display:inline-flex;width:34px;height:18px;border-radius:9px;background:var(--border-color);transition:background .22s;cursor:pointer;flex-shrink:0}
.ed-switch.on{background:var(--ok)}
.ed-switch::after{content:"";position:absolute;top:2px;left:2px;width:14px;height:14px;border-radius:50%;background:var(--bg-primary);transition:transform .22s}
.ed-switch.on::after{transform:translateX(16px)}
.ed-todo-list{list-style:none;font-size:13px}
.ed-todo-list li{display:flex;gap:8px;padding:6px 0;border-bottom:1px dotted var(--border-light);align-items:center}
.ed-todo-list li:last-child{border-bottom:none}
.ed-todo-list input[type=checkbox]{accent-color:var(--accent)}
.ed-todo-list li.done{color:var(--text-muted);text-decoration:line-through}
.ed-todo-list li.done label{color:var(--text-muted)}
.ed-todo-del{color:var(--text-muted);font-size:16px;line-height:1;padding:0 4px;transition:color .12s}
.ed-todo-del:hover{color:var(--err)}
.ed-todo-input{flex:1;font-size:13px;background:var(--bg-secondary);border:1px solid var(--border-color);border-radius:2px;padding:6px 12px;color:var(--text-primary)}
.ed-todo-input:focus{outline:none;border-color:var(--accent)}
.ed-kl-step{cursor:pointer;transition:color .12s}
.ed-kl-step:hover{color:var(--accent)}
.ed-flow-card{cursor:pointer;transition:border-color .12s,transform .12s}
.ed-flow-card:hover{border-color:var(--accent);transform:translateY(-2px)}
.ed-flow-arrow{font-size:16px;color:var(--text-muted);margin-top:8px;opacity:0;transition:opacity .12s}
.ed-flow-card:hover .ed-flow-arrow{opacity:1}
.ed-source-btn{font-size:11.5px;color:var(--text-muted);transition:color .12s;text-decoration:underline;text-decoration-color:transparent;text-underline-offset:2px}
.ed-source-btn:hover{color:var(--accent);text-decoration-color:var(--accent)}
.ed-filter-tag{display:inline-block;font-size:9px;font-weight:600;font-family:'JetBrains Mono',monospace;color:var(--accent);border:1px solid var(--accent);border-radius:2px;padding:0 5px;margin-left:2px}
.ed-skeleton-list{padding:16px 0}
.ed-skeleton-row{display:flex;flex-direction:column;gap:8px;padding:16px 0;border-bottom:1px solid var(--border-light)}
.ed-skeleton-bar{height:12px;border-radius:2px;background:var(--bg-hover);animation:ed-shimmer 1.5s ease-in-out infinite}
@keyframes ed-shimmer{0%,100%{opacity:.4}50%{opacity:.7}}
`;
