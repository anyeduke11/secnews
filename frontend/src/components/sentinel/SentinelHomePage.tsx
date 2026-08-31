/**
 * SentinelHomePage — 哨兵终端 · 资料层首页 (V2 设计稿 data 屏)
 *
 * 信息架构: 三层工作流的资料层 — 采集与组织。
 * 壳 (appbar + 心跳条) 由 SentinelShell 提供, 本页聚焦:
 *  - 阅读模式四态 (简报/扫描/深度/告警) + 频道 chips
 *  - 全文搜索 / 时间范围切换 / 游标分页 / 收藏加星 (报纸版能力移植)
 *  - 头条叙事 + 次级重点 + 快讯流 (+ 可展开高危告警)
 *  - 右栏: 源监控 / 质量门禁 24h / 今日行动
 *
 * 数据源 (全部真实 API):
 *  - GET /api/hotspots?category&time_range&keyword&limit&cursor —— 经 useHotspotData
 *  - GET/POST/DELETE /api/favorites —— 经 useFavorites (模块级单例 store)
 *  - GET /api/quality/summary · GET /api/todos (右栏)
 *  - SSE /api/events (collect 完成后节流刷新)
 */
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useSSE } from '../../hooks/useSSE';
import { useHotspotData } from '../../hooks/useHotspotData';
import { useFavorites } from '../../hooks/useFavorites';
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

/**
 * 时间窗 chips —— 权威枚举见 backend/domain/enums.py::TimeRange (仅这 4 个值)。
 * `1d` 不在枚举内 (会 400), 因此这里刻意只用 `24h`。
 * `7d` 的语义是「本周周一 00:00 起」而非滚动 7 天, 文案与 title 如实反映。
 */
const TIME_RANGE_DEFS: { id: string; label: string; hint: string }[] = [
  { id: '24h', label: '24H', hint: '回溯最近 24 小时' },
  { id: '3d', label: '3D', hint: '回溯最近 72 小时' },
  { id: '7d', label: '本周', hint: '本周周一 00:00 起算, 不是滚动 7 天' },
  { id: '30d', label: '30D', hint: '回溯最近 30 天' },
];

/** 关键词防抖 (ms): 避免每次按键都打一次 /api/hotspots */
const KEYWORD_DEBOUNCE_MS = 300;

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

/** API 来源 href 白名单: 只放行 http(s), javascript:/data: 一律不渲染链接 */
function safeHref(url: string | null | undefined): string | null {
  if (typeof url !== 'string') return null;
  return /^https?:\/\/\S+$/i.test(url.trim()) ? url.trim() : null;
}

/** 必须是独立组件: 在 SentinelHomePage 函数体内调用 usePipe 会落在 Provider 之外, 永远读到 null */
function RailWithPipe({ quality, todos }: { quality: QualitySummaryRaw | null; todos: TodoRow[] }) {
  const { pipe } = usePipe();
  return <SentinelRail sources={pipe?.sources ?? []} quality={quality} todos={todos} />;
}

/**
 * URL 导入入库 (POST /api/kl/import/url) — 迁移自 workbench/AnalyzeView。
 * 后端 ImportUrlRequest 只有 `url: str`, 不做 scheme 校验, 也不校验重复,
 * 所以这里必须自己挡住非 http(s) 输入, 否则会往库里造垃圾条目。
 * 旧实现在 catch 里静默失败, 用户看不到任何反馈 —— 这里改为显式报错。
 */
function UrlImport({ onDone }: { onDone: () => void }) {
  const [open, setOpen] = useState(false);
  const [url, setUrl] = useState('');
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<{ kind: 'ok' | 'err'; text: string } | null>(null);

  const valid = /^https?:\/\/\S+$/i.test(url.trim());

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!valid || busy) return;
    setBusy(true);
    setMsg(null);
    try {
      const r = await fetch('/api/kl/import/url', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
        body: JSON.stringify({ url: url.trim() }),
      });
      if (!r.ok) {
        setMsg({ kind: 'err', text: `导入失败 (${r.status})` });
        return;
      }
      const data = (await r.json()) as { id?: string };
      setMsg({ kind: 'ok', text: `已入库 ${data.id ?? ''} · kl:raw` });
      setUrl('');
      onDone();
    } catch {
      setMsg({ kind: 'err', text: '导入失败: 网络或后端不可达' });
    } finally {
      setBusy(false);
    }
  }

  return (
    <span className="sn-import">
      <button
        type="button"
        className="btn-ghost"
        aria-expanded={open}
        onClick={() => setOpen(o => !o)}
      >
        导入 URL
      </button>
      {open && (
        <form className="sn-import-form" onSubmit={submit}>
          <input
            type="url"
            className="editorial-input"
            style={{ width: 260 }}
            placeholder="https://example.com/article"
            aria-label="待导入的文章 URL"
            value={url}
            onChange={e => { setUrl(e.target.value); setMsg(null); }}
            autoComplete="off"
          />
          <button type="submit" className="btn-primary" disabled={!valid || busy}>
            {busy ? '导入中' : '导入'}
          </button>
          <span className="sn-import-msg num" aria-live="polite">
            {msg?.text ?? (url && !valid ? '需以 http:// 或 https:// 开头' : '')}
          </span>
        </form>
      )}
    </span>
  );
}

/** 加星按钮: 样式类复用 index.css 的 .agihunt-card-star, 颜色走 --sn-* token */
function StarButton({ item, fav, onToggle }: { item: HotspotItem; fav: boolean; onToggle: (item: HotspotItem) => void }) {
  return (
    <button
      type="button"
      className="agihunt-card-star"
      style={{ color: fav ? 'var(--sn-mint)' : 'var(--sn-ink-3)' }}
      title={fav ? '取消收藏' : '收藏'}
      aria-label={`${fav ? '取消收藏' : '收藏'}：${item.title}`}
      aria-pressed={fav}
      onClick={e => { e.stopPropagation(); onToggle(item); }}
    >
      <svg width="13" height="13" viewBox="0 0 24 24" fill={fav ? 'currentColor' : 'none'} stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
        <polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2" />
      </svg>
    </button>
  );
}

/** tag 右侧的"进入深度阅读"金黄入口, 跳转后由 DeepReadPage 自动开始分析 */
function DeepReadChip({ id, label = '深读', itemTitle }: { id: string; label?: string; itemTitle?: string }) {
  const navigate = useNavigate();
  return (
    <button
      type="button"
      className="dr-link"
      title="进入深度阅读"
      aria-label={itemTitle ? `对「${itemTitle}」进入深度阅读` : undefined}
      onClick={e => { e.stopPropagation(); navigate(`/deep/hotspot/${id}`); }}
    >
      {label}
      <svg width="12" height="12" viewBox="0 0 14 14" fill="none" aria-hidden="true"><path d="M2.5 7h8M7.5 3.5L11 7l-3.5 3.5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" /></svg>
    </button>
  );
}

export function SentinelHomePage() {
  const navigate = useNavigate();

  const [mode, setMode] = useState<ReadMode>('brief');
  const [channel, setChannel] = useState('all');
  const [timeRange, setTimeRange] = useState('24h');

  // 搜索框受控值 (即时反馈) 与实际下发给 hook 的防抖值
  const [keywordInput, setKeywordInput] = useState('');
  const [keyword, setKeyword] = useState('');

  const [quality, setQuality] = useState<QualitySummaryRaw | null>(null);
  const [todos, setTodos] = useState<TodoRow[]>([]);

  const reloadPipe = usePipeReloadOnSse();

  // SSE 事件可能高频, 对 refresh() 做一层节流, 避免翻页缓存被反复清空。
  // ref 必须在 useSSE 之前声明 (回调在渲染期即被持有), 具体实现见下方赋值。
  const refreshTimerRef = useRef<number | null>(null);
  const refreshDebouncedRef = useRef<() => void>(() => {});

  // ── 资料层主数据: 全文搜索 + 时间窗 + cursor 分页统一由 hook 负责 ──
  const {
    items, total, categoryCounts, loading, loadingPage, error,
    hasMore, page, pageSize, totalPages, setPage, refresh,
    latestIngestionCount, latestIngestionAt,
  } = useHotspotData(channel, timeRange, keyword);

  refreshDebouncedRef.current = () => {
    if (refreshTimerRef.current !== null) return;
    refreshTimerRef.current = window.setTimeout(() => {
      refreshTimerRef.current = null;
      void refresh();
    }, 3000);
  };
  useEffect(() => () => {
    if (refreshTimerRef.current !== null) window.clearTimeout(refreshTimerRef.current);
  }, []);

  // ── 收藏: 模块级单例 store, 乐观更新 + 失败回滚 ──
  const { count: favoriteCount, isFavorite, toggleFavorite } = useFavorites();

  useEffect(() => {
    if (keywordInput === keyword) return;
    const t = window.setTimeout(() => setKeyword(keywordInput), KEYWORD_DEBOUNCE_MS);
    return () => window.clearTimeout(t);
  }, [keywordInput, keyword]);

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
    loadSide();
  }, [loadSide]);

  // SSE: collect 相关事件 → 节流刷新 (10s)
  useSSE({
    onEvent: () => {
      reloadPipe();
      loadSide();
      refreshDebouncedRef.current();
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

  // 「今日收录」口径: 后端 time_range=24h 即"今日 00:00 起"; 换频道/放宽时间窗/搜索后
  // total 已不是当日语义, 改标「范围内 / 匹配」, 心跳条该格回退为 '…' 避免误导。
  const isTodayScope = channel === 'all' && timeRange === '24h' && !keyword;
  const scopeLabel = keyword ? '匹配' : isTodayScope ? '今日收录' : '范围内';
  const ingestedForHeader = isTodayScope ? total : null;

  const star = useCallback((item: HotspotItem) => { void toggleFavorite(item); }, [toggleFavorite]);

  const goPrev = useCallback(() => setPage(page - 1), [page, setPage]);
  const goNext = useCallback(() => setPage(page + 1), [page, setPage]);

  return (
    <SentinelShell layer="data" mode={mode} ingested={ingestedForHeader}>
      {/* ===== 阅读模式 & 频道条 ===== */}
      <div className="controlbar">
        <div className="modes" role="group" aria-label="阅读模式">
          {([['brief', '简报'], ['scan', '扫描'], ['deep', '深度']] as const).map(([m, label]) => (
            <button key={m} className="mode-btn" aria-pressed={mode === m} onClick={() => setMode(m)}>{label}</button>
          ))}
          <button className="mode-btn mode-alert-on" aria-pressed={mode === 'alert'} onClick={() => setMode('alert')}>告警</button>
        </div>
        <nav className="channels" aria-label="内容频道">
          {CHANNEL_DEFS.map(ch => {
            const n = ch.id === 'all' ? total : categoryCounts[ch.id] ?? 0;
            return (
              <button
                key={ch.id}
                className={`chip${channel === ch.id ? ' active' : ''}`}
                style={{ '--sn-dot': ch.color } as React.CSSProperties}
                aria-pressed={channel === ch.id}
                onClick={() => setChannel(ch.id)}
              >
                <i aria-hidden="true" />{ch.label}
                {n > 0 && <span className="num">{n}</span>}
              </button>
            );
          })}
        </nav>
      </div>

      {/* ===== 检索条: 全文搜索 + 时间窗 ===== */}
      <div
        className="controlbar"
        style={{ top: 52, zIndex: 49, height: 'auto', minHeight: 52, padding: '10px 32px', gap: 12, flexWrap: 'wrap' }}
      >
        <div className="search-box" style={{ maxWidth: 320, width: 'auto', flex: '1 1 220px', minWidth: 180 }}>
          <span className="search-icon" aria-hidden="true" style={{ display: 'flex', alignItems: 'center' }}>
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round"><circle cx="11" cy="11" r="8" /><line x1="21" y1="21" x2="16.65" y2="16.65" /></svg>
          </span>
          <input
            type="search"
            name="sentinel-hotspot-search"
            value={keywordInput}
            onChange={e => setKeywordInput(e.target.value)}
            placeholder="搜索标题 / 摘要（中文按子串匹配）"
            aria-label="搜索热点关键词"
            autoComplete="off"
          />
          {keywordInput && (
            <button type="button" className="search-clear" aria-label="清空搜索" onClick={() => { setKeywordInput(''); setKeyword(''); }}>
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden="true"><line x1="18" y1="6" x2="6" y2="18" /><line x1="6" y1="6" x2="18" y2="18" /></svg>
            </button>
          )}
        </div>

        <span style={{ display: 'flex', alignItems: 'center', gap: 4 }} role="group" aria-label="时间范围">
          {TIME_RANGE_DEFS.map(t => (
            <button
              key={t.id}
              type="button"
              className={`chip num${timeRange === t.id ? ' active' : ''}`}
              title={t.hint}
              aria-pressed={timeRange === t.id}
              onClick={() => setTimeRange(t.id)}
            >
              {t.label}
            </button>
          ))}
        </span>

        <UrlImport onDone={refresh} />

        <span className="flash-count num" style={{ marginLeft: 'auto' }} title="时间窗语义以后端 TimeRange 为准；收藏数取自 /api/favorites（上限 1000 条）">
          {scopeLabel} {total} 篇 · 第 {page}/{totalPages} 页 · 收藏 ≤{favoriteCount}
          {loadingPage ? ' · 翻页中' : ''}
        </span>
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
              <button className="empty-cta" onClick={() => void refresh()}>重试
                <svg width="14" height="14" viewBox="0 0 14 14" fill="none" aria-hidden="true"><path d="M2.5 7a4.5 4.5 0 1 1 1.3 3.2M2.5 7V4M2.5 7h3" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" /></svg>
              </button>
            </div>
          ) : items.length === 0 ? (
            <div className="empty-panel">
              <div className="empty-ring" aria-hidden="true">
                <svg width="20" height="20" viewBox="0 0 20 20" fill="none"><path d="M10 2.5l2 4.5 4.5.7-3.2 3.2.7 4.8L10 13.6l-4 2.1.7-4.8L3.5 7.7 8 7l2-4.5z" stroke="currentColor" strokeWidth="1.3" strokeLinejoin="round" /></svg>
              </div>
              <h3>{keyword ? '没有匹配的条目' : '该范围暂无收录'}</h3>
              <p>{keyword
                ? `关键词「${keyword}」在当前频道与时间窗内没有命中，换个说法或放宽时间范围试试。`
                : '采集管线每 5 分钟自动运行一轮，也可手动触发一轮立即补采。'}</p>
              <button className="empty-cta" onClick={async () => { await refresh(); loadSide(); reloadPipe(); }}>立即采集
                <svg width="14" height="14" viewBox="0 0 14 14" fill="none" aria-hidden="true"><path d="M2.5 7h8M7.5 3.5L11 7l-3.5 3.5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" /></svg>
              </button>
            </div>
          ) : (
            <>
              {/* 头条 */}
              {lead && safeHref(lead.url) && (
                <article className="story-top">
                  <div className="meta-row">
                    <span className="tag" style={{ '--sn-tag-c': tagColorOf(lead.category) } as React.CSSProperties}><i aria-hidden="true" />{labelOf(lead.category)}</span>
                    <DeepReadChip id={lead.id} label="进入深度阅读" itemTitle={lead.title} />
                    <span className="src">{lead.source}</span>
                    <span className="time num">{relTime(lead.published_at)}</span>
                    <span className="time num">评分 {Math.round(lead.score ?? lead.quality_score ?? 0)}</span>
                  </div>
                  <h1 className="headline">
                    <a href={safeHref(lead.url)!} target="_blank" rel="noopener noreferrer">{lead.title}</a>
                  </h1>
                  {lead.summary && <p className="standfirst">{lead.summary}</p>}
                  <div className="head-foot">
                    <div className="heatbox" aria-label={`当前热度 ${heatOf(lead)} / 5`}>
                      <span className="heat-cells" aria-hidden="true">
                        {heatCells(heatOf(lead)).map((on, i) => <b key={i} className={on ? 'on' : undefined} />)}
                      </span>
                      <span className="heat-num">{heatOf(lead)}/5</span>
                    </div>
                    <StarButton item={lead} fav={isFavorite(lead.id)} onToggle={star} />
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
                        {safeHref(item.url) ? (
                          <a href={safeHref(item.url)!} target="_blank" rel="noopener noreferrer"><div className="sub-title">{item.title}</div></a>
                        ) : (
                          <div className="sub-title">{item.title}</div>
                        )}
                        <div className="sub-meta">
                          <span className="src">{item.source}</span>
                          <span className="time num">{relTime(item.published_at)}</span>
                          <span className="mini-heat" aria-hidden="true">
                            {heatCells(heatOf(item)).map((on, i) => <b key={i} className={on ? 'on' : undefined} />)}
                          </span>
                          <span className="ftag" style={{ color: tagColorOf(item.category), background: 'transparent', border: '1px solid var(--sn-line)' }}>{labelOf(item.category)}</span>
                          <DeepReadChip id={item.id} itemTitle={item.title} />
                          <StarButton item={item} fav={isFavorite(item.id)} onToggle={star} />
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
                  <span className="flash-count num">
                    PAGE {page} · {items.length} ITEMS
                    {latestIngestionCount ? ` · 最近一轮 +${latestIngestionCount}` : ''}
                    {latestIngestionAt ? ` · ${relTime(latestIngestionAt)}` : ''}
                  </span>
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
                          {safeHref(alertItem.url) && (
                            <button className="abtn" onClick={() => window.open(safeHref(alertItem.url)!, '_blank', 'noopener')}>查看原文</button>
                          )}
                          <StarButton item={alertItem} fav={isFavorite(alertItem.id)} onToggle={star} />
                        </div>
                      </div>
                    </li>
                  )}

                  {/* 常规快讯 */}
                  {flashes.map(item => {
                    const href = safeHref(item.url);
                    return (
                      <li className="flash-item" key={item.id}>
                        <span className="flash-time num">{relTime(item.published_at)}</span>
                        <div className="flash-body">
                          {href ? (
                            <a href={href} target="_blank" rel="noopener noreferrer"><span className="flash-title">{item.title}</span></a>
                          ) : (
                            <span className="flash-title">{item.title}</span>
                          )}
                          <span className="flash-tags"><span className="ftag" style={{ color: tagColorOf(item.category) }}>{labelOf(item.category)}</span><DeepReadChip id={item.id} itemTitle={item.title} /></span>
                        </div>
                        <div className="flash-side">
                          <span className="flash-src">{item.source}</span>
                          <span className="mini-heat" aria-hidden="true">
                            {heatCells(heatOf(item)).map((on, i) => <b key={i} className={on ? 'on' : undefined} />)}
                          </span>
                        </div>
                        <StarButton item={item} fav={isFavorite(item.id)} onToggle={star} />
                      </li>
                    );
                  })}
                </ul>

                {/* 游标分页控件 */}
                <div
                  style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 10, flexWrap: 'wrap', paddingTop: 18 }}
                >
                  <button
                    type="button"
                    className="pagination-btn"
                    aria-label="上一页"
                    disabled={page <= 1 || loadingPage}
                    onClick={goPrev}
                  >
                    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><polyline points="15 18 9 12 15 6" /></svg>
                    <span>上一页</span>
                  </button>
                  <span className="page-indicator" aria-live="polite">
                    第 <strong>{page}</strong> / {totalPages} 页 · 共 {total} 篇
                  </span>
                  <button
                    type="button"
                    className="pagination-btn"
                    aria-label="下一页"
                    disabled={!hasMore || loadingPage}
                    onClick={goNext}
                  >
                    <span>下一页</span>
                    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><polyline points="9 18 15 12 9 6" /></svg>
                  </button>
                </div>
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
        <span>{scopeLabel} {total} 篇 · 每页 {pageSize}</span>
      </footer>
    </SentinelShell>
  );
}
