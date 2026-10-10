/**
 * SentinelHomePage — 哨兵终端 · 资料层首页 (V2 设计稿 data 屏)
 *
 * 信息架构: 三层工作流的资料层 — 采集与组织。
 * 壳 (appbar + 心跳条) 由 SentinelShell 提供, 本页聚焦:
 *  - 阅读模式四态 (全量/精选/深度/告警) + 频道 chips
 *  - 全文搜索 / 时间范围切换 / 游标分页 / 收藏加星 (报纸版能力移植)
 *  - 精选视图 = /api/hotspots/picked 按 pick_score DESC Top-N (P2 2026-09-27);
 *    深度视图 = 当前条目长文过滤 (summary≥200 或 title 命中深度词)
 *  - 头条叙事 + 次级重点 + 快讯流 (alert 模式渲染真告警列表 NewsAlertList, P1 2026-09-27)
 *  - 右栏: 源监控 / 质量门禁 24h / 今日行动
 *
 * 数据源 (全部真实 API):
 *  - GET /api/hotspots?category&time_range&keyword&limit&cursor —— 经 useHotspotData
 *  - GET/POST/DELETE /api/favorites —— 经 useFavorites (模块级单例 store)
 *  - GET /api/quality/summary · GET /api/todos (右栏)
 *  - GET /api/settings/refresh-interval (页脚/空态展示真实采集间隔)
 *  - SSE /api/events (经 src/hooks/realtime.ts 统一注册, 只订阅 collect_done: 采集完成后只读重拉, 不再回触 POST /api/refresh)
 *
 * 刷新节奏契约 (cadence 修正批, 2026-09-10):
 *  - 后端按 settings 里的采集间隔跑 collect_all; 一轮结束发一次 collect_done
 *  - 首页只在 collect_done 或用户手动点「立即采集」时变化; SSE 路径绝不触发采集,
 *    否则 "采集 → collect_done → POST /api/refresh → 再采集" 会形成自激循环,
 *    把 30 分钟节奏打成连续抓取 (owner 反馈"首页刷新频率过高"的根因)
 */
import { useCallback, useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { SSE_EVENTS, useRealtimeInvalidation } from '../../hooks/realtime';
import { useHotspotData } from '../../hooks/useHotspotData';
import { useFavorites } from '../../hooks/useFavorites';
import { useReactions, type ReactionType } from '../../hooks/useReactions';
import { CATEGORIES, HotspotItem, PRACTICE_DOMAIN_LABELS, plainSummary } from '../../types';
import { getJSON, postJSON } from '../../lib/api';
import { getNewsAlertUnread, getPickedItems, PickedItem } from '../../api/secnews';
import { PriorityDigestCard } from './PriorityDigestCard';
import { NewsAlertList } from './NewsAlertList';
import { ReactionButtons } from './ReactionButtons';
import { SentinelShell, usePipe, usePipeReloadOnSse } from './SentinelShell';
import { SentinelRail } from './SentinelRail';
import { SignalPanel } from '../v1/panels/SignalPanel';
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
  // DEV-0175: bid (招投标) 已随工作台聚焦裁决剔除
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

/** 后端默认采集间隔 (分钟), 与 useRefreshInterval.DEFAULT_MINUTES / config 默认值一致; 仅在接口不可达时兜底展示 */
const DEFAULT_COLLECT_MINUTES = 30;

/** SSE collect_done 后右栏 (质量门禁 / 待办) 的重拉节流窗口 (ms) — 与心跳条 usePipeReloadOnSse 同频 */
const SIDE_RELOAD_GATE_MS = 10_000;

/** 分类 → tag 颜色 (story-top / 次级 / 快讯标签) */
function tagColorOf(category: string): string {
  switch (category) {
    case 'ai': return 'var(--sn-cat-ai)';
    case 'ai_security': return 'var(--sn-cat-ai)';
    case 'security': return 'var(--sn-cat-sec)';
    case 'finance': return 'var(--sn-cat-fin)';
    case 'startup': return 'var(--sn-cat-vc)';
    case 'github': return 'var(--sn-cat-git)';
    case 'tech': return 'var(--sn-cat-tech)';
    // 论文: 紫色系复用现有 token (startup 紫), 不新造 CSS 变量
    case 'paper': return 'var(--sn-cat-vc)';
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
      // apiFetch 非 ok 抛错 → catch 显式报错 (message 为后端 detail; 原实现拼接 HTTP 状态)
      const data = await postJSON<{ id?: string }>('/api/kl/import/url', { url: url.trim() });
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

/** 快讯行: brief 快讯流与 deep 深度视图共用同一行结构 (P2 2026-09-27 抽取) */
function FlashRow({ item, interestDomains, fav, onStar, reaction, onReact, showReactions }: {
  item: HotspotItem;
  interestDomains: string[];
  fav: boolean;
  onStar: (item: HotspotItem) => void;
  reaction?: ReactionType;
  onReact: (item: HotspotItem, type: ReactionType) => void;
  showReactions: boolean;
}) {
  const href = safeHref(item.url);
  return (
    <li className="flash-item">
      <span className="flash-time num">{relTime(item.published_at)}</span>
      <div className="flash-body">
        {href ? (
          <a href={href} target="_blank" rel="noopener noreferrer"><span className="flash-title">{item.title}</span></a>
        ) : (
          <span className="flash-title">{item.title}</span>
        )}
        <span className="flash-tags">
          <span className="ftag" style={{ color: tagColorOf(item.category) }}>{labelOf(item.category)}</span>
          {item.practice_domain && (
            <span
              className="ftag"
              title={interestDomains.includes(item.practice_domain) ? '命中你的兴趣方向, 已优先展示' : '实践域'}
              style={interestDomains.includes(item.practice_domain)
                ? { color: 'var(--sn-mint, #00e5a0)', border: '1px solid var(--sn-mint, #00e5a0)' }
                : undefined}
            >
              {PRACTICE_DOMAIN_LABELS[item.practice_domain] || item.practice_domain}
            </span>
          )}
          <DeepReadChip id={item.id} itemTitle={item.title} />
        </span>
      </div>
      <div className="flash-side">
        <span className="flash-src">{item.source}</span>
        <span className="mini-heat" aria-hidden="true">
          {heatCells(heatOf(item)).map((on, i) => <b key={i} className={on ? 'on' : undefined} />)}
        </span>
      </div>
      {showReactions && <ReactionButtons item={item} current={reaction} onReact={onReact} />}
      <StarButton item={item} fav={fav} onToggle={onStar} />
    </li>
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
  const [collectMinutes, setCollectMinutes] = useState<number>(DEFAULT_COLLECT_MINUTES);

  const reloadPipe = usePipeReloadOnSse();

  // ── 资料层主数据: 全文搜索 + 时间窗 + cursor 分页统一由 hook 负责 ──
  const {
    items, total, categoryCounts, loading, loadingPage, error,
    hasMore, page, pageSize, totalPages, setPage, refresh, refetch,
    latestIngestionCount, latestIngestionAt, interestDomains,
  } = useHotspotData(channel, timeRange, keyword);

  // ── 收藏: 模块级单例 store, 乐观更新 + 失败回滚 ──
  const { count: favoriteCount, isFavorite, toggleFavorite } = useFavorites();
  // DEV-0311: 赞/踩 (available=false 时隐藏按钮组, 不渲染死键)
  const { reactionOf, react: reactItem, available: reactionsAvailable } = useReactions();

  useEffect(() => {
    if (keywordInput === keyword) return;
    const t = window.setTimeout(() => setKeyword(keywordInput), KEYWORD_DEBOUNCE_MS);
    return () => window.clearTimeout(t);
  }, [keywordInput, keyword]);

  // 右栏数据 (一次性 + SSE 刷新时重拉)
  const loadSide = useCallback(async () => {
    try {
      // apiFetch 非 ok 抛错 → 失败的一路置 null / 空 (对应原 r.ok 分支检查)
      const [qs, ts] = await Promise.all([
        getJSON<QualitySummaryRaw>('/api/quality/summary').catch(() => null),
        getJSON<{ items?: TodoRow[] }>('/api/todos').catch(() => ({ items: [] as TodoRow[] })),
      ]);
      setQuality(qs);
      setTodos(((ts.items || []) as TodoRow[]).filter(i => i.status !== 'done').slice(0, 6));
    } catch { /* 右栏失败不阻塞主列 */ }
  }, []);

  useEffect(() => {
    loadSide();
  }, [loadSide]);

  // 真实采集间隔 (分钟): 供页脚 / 空态文案, 与 /settings 里的选择保持一致
  useEffect(() => {
    let alive = true;
    getJSON<{ interval_minutes?: number } | null>('/api/settings/refresh-interval')
      .then(d => {
        if (alive && d && typeof d.interval_minutes === 'number' && d.interval_minutes > 0) {
          setCollectMinutes(d.interval_minutes);
        }
      })
      .catch(() => { /* 接口不可达时保留默认值展示 */ });
    return () => { alive = false; };
  }, []);

  // 告警未读徽标 (scope=news 4 规则域): 挂载拉一次 + SSE news_alert 刷新
  const [newsUnread, setNewsUnread] = useState(0);
  const reloadNewsUnread = useCallback(() => {
    getNewsAlertUnread()
      .then(d => setNewsUnread(d.count))
      .catch(() => { /* 接口不可达时保留现值 */ });
  }, []);
  useEffect(() => { reloadNewsUnread(); }, [reloadNewsUnread]);

  // ── 精选视图 (P2 2026-09-27): 独立数据源 /api/hotspots/picked ──
  // 切到 scan 模式时拉取; pick_refresh SSE 已裁剪 (计划 Self-Review #1):
  // 精选列表 30min 采集粒度足够, 重进 scan 即重拉, 不新增事件类型。
  const [picked, setPicked] = useState<PickedItem[] | null>(null);
  useEffect(() => {
    if (mode !== 'scan') return;
    let alive = true;
    getPickedItems()
      .then(d => { if (alive) setPicked(d.items); })
      .catch(() => { if (alive) setPicked([]); }); // 接口失败 → 诚实空态, 不阻塞页面
    return () => { alive = false; };
  }, [mode]);

  // ── 深度视图 (P2): 当前条目长文过滤 (纯前端, spec §4) ──
  const deepItems = useMemo(
    () => items.filter(i => (i.summary?.length ?? 0) >= 200 || /分析|详解|深度|指南|research/.test(i.title)),
    [items],
  );

  // SSE: 只响应 collect_done (一轮采集只发一次)。其余事件 (埋点 / extract_done / alert /
  // job_done …) 与资料层无关, 不刷页面。三条动作沿用 cadence 修正批 (2026-09-10) 的窗口,
  // 经 src/hooks/realtime.ts 统一注册器路由, 全部只读重拉:
  //  - 心跳条: usePipeReloadOnSse 内部自带 10s 节流 + mountedReload 优先 (DEV-0167)
  //  - 右栏 (质量门禁 / 待办): 10s 节流, 兜底重连回放多条的情况
  //  - 主列: 3s 合并 (重连回放可能连发多条 collect_done), 避免翻页缓存被反复清空
  useRealtimeInvalidation([
    { types: SSE_EVENTS.COLLECT_DONE, handler: () => reloadPipe() },
    { types: SSE_EVENTS.COLLECT_DONE, handler: () => void loadSide(), throttleMs: SIDE_RELOAD_GATE_MS },
    { types: SSE_EVENTS.COLLECT_DONE, handler: () => void refetch(), debounceMs: 3000 },
    { types: SSE_EVENTS.NEWS_ALERT, handler: reloadNewsUnread },
  ]);

  const [lead, secondaries, flashes] = useMemo(
    () => [items[0] ?? null, items.slice(1, 3), items.slice(3)],
    [items],
  );

  // 「今日收录」口径: 后端 time_range=24h 即"今日 00:00 起"; 换频道/放宽时间窗/搜索后
  // total 已不是当日语义, 改标「范围内 / 匹配」, 心跳条该格回退为 '…' 避免误导。
  const isTodayScope = channel === 'all' && timeRange === '24h' && !keyword;
  const scopeLabel = keyword ? '匹配' : isTodayScope ? '今日收录' : '范围内';
  const ingestedForHeader = isTodayScope ? total : null;

  const star = useCallback((item: HotspotItem) => { void toggleFavorite(item); }, [toggleFavorite]);
  const doReact = useCallback((item: HotspotItem, type: ReactionType) => { void reactItem(item, type); }, [reactItem]);

  const goPrev = useCallback(() => setPage(page - 1), [page, setPage]);
  const goNext = useCallback(() => setPage(page + 1), [page, setPage]);

  return (
    <SentinelShell layer="data" mode={mode} ingested={ingestedForHeader}>
      {/* ===== 阅读模式 & 频道条 ===== */}
      <div className="controlbar">
        <div className="modes" role="group" aria-label="阅读模式">
          {([['brief', '全量'], ['scan', '精选'], ['deep', '深度']] as const).map(([m, label]) => (
            <button key={m} className="mode-btn" aria-pressed={mode === m} onClick={() => setMode(m)}>{label}</button>
          ))}
          <button className="mode-btn mode-alert-on" aria-pressed={mode === 'alert'} onClick={() => setMode('alert')}>告警
            {newsUnread > 0 && <span className="alert-unread-badge" aria-label={`${newsUnread} 条未读告警`}>{newsUnread}</span>}
          </button>
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
        style={{ top: 'calc(var(--sn-bandnav-h) + 52px)', zIndex: 49, height: 'auto', minHeight: 52, padding: '10px 32px', gap: 12, flexWrap: 'wrap' }}
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

        <UrlImport onDone={() => { void refetch(); }} />

        <span className="flash-count num" style={{ marginLeft: 'auto' }} title="时间窗语义以后端 TimeRange 为准；收藏数取自 /api/favorites（上限 1000 条）">
          {scopeLabel} {total} 篇 · 第 {page}/{totalPages} 页 · 收藏 ≤{favoriteCount}
          {loadingPage ? ' · 翻页中' : ''}
        </span>
      </div>

      {/* ===== 主布局 ===== */}
      <div className="layout">
        <main className="maincol">
          {mode === 'scan' ? (
            /* 精选视图 (P2 2026-09-27): 独立数据源, 自带加载/空态, 不混排常规快讯流 */
            picked === null ? (
              <div className="story-top" aria-busy="true">
                <div className="skel-line w1" /><div className="skel-line w2" /><div className="skel-line w3" /><div className="skel-line w2" />
              </div>
            ) : picked.length === 0 ? (
              <div className="empty-panel">
                <div className="empty-ring" aria-hidden="true">
                  <svg width="20" height="20" viewBox="0 0 20 20" fill="none"><path d="M10 2.5l2 4.5 4.5.7-3.2 3.2.7 4.8L10 13.6l-4 2.1.7-4.8L3.5 7.7 8 7l2-4.5z" stroke="currentColor" strokeWidth="1.3" strokeLinejoin="round" /></svg>
                </div>
                <h3>暂无精选</h3>
                <p>下一轮采集后生成 — pick_score 由采集尾部落列。</p>
              </div>
            ) : (
              <section aria-label="精选资讯">
                <div className="flash-head">
                  <h2>精选资讯</h2>
                  <span className="flash-count num">{picked.length} ITEMS · PICK SCORE DESC</span>
                </div>
                <ul className="flash-list">
                  {picked.map(item => {
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
                          <span className="flash-tags">
                            <span className="pick-badge">精选</span>
                            <span className="pick-score num" title="pick_score = 质量 + 关注域 + 收藏源 + 时效">{item.pick_score}</span>
                            <span className="ftag" style={{ color: tagColorOf(item.category) }}>{labelOf(item.category)}</span>
                          </span>
                        </div>
                        <div className="flash-side">
                          <span className="flash-src">{item.source}</span>
                        </div>
                      </li>
                    );
                  })}
                </ul>
              </section>
            )
          ) : loading ? (
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
              <button className="empty-cta" onClick={() => void refetch()}>重试
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
                : `采集管线每 ${collectMinutes} 分钟自动运行一轮，也可手动触发一轮立即补采。`}</p>
              <button className="empty-cta" onClick={async () => { await refresh(); void loadSide(); reloadPipe(); }}>立即采集
                <svg width="14" height="14" viewBox="0 0 14 14" fill="none" aria-hidden="true"><path d="M2.5 7h8M7.5 3.5L11 7l-3.5 3.5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" /></svg>
              </button>
            </div>
          ) : mode === 'deep' ? (
            /* 深度视图 (P2 2026-09-27): 长文候选过滤, 纯前端 */
            deepItems.length === 0 ? (
              <div className="empty-panel">
                <div className="empty-ring" aria-hidden="true">
                  <svg width="20" height="20" viewBox="0 0 20 20" fill="none"><path d="M10 5v5l3 3" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" /><circle cx="10" cy="10" r="7.5" stroke="currentColor" strokeWidth="1.5" /></svg>
                </div>
                <h3>当前无深读候选</h3>
                <p>在条目上收藏后归入深读。</p>
              </div>
            ) : (
              <section aria-label="深度阅读">
                <div className="flash-head">
                  <h2>深度阅读</h2>
                  <span className="flash-count num">{deepItems.length} ITEMS · 长文候选</span>
                </div>
                <ul className="flash-list">
                  {deepItems.map(item => (
                    <FlashRow key={item.id} item={item} interestDomains={interestDomains} fav={isFavorite(item.id)} onStar={star} reaction={reactionOf(item.id)} onReact={doReact} showReactions={reactionsAvailable} />
                  ))}
                </ul>
              </section>
            )
          ) : (
            <>
              {/* DEV-0177 T0.5 收敛: SK-01 今日重点情报 (实践域分区) */}
              <PriorityDigestCard />
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
                  {(() => { const s = plainSummary(lead.summary); return s ? <p className="standfirst">{s}</p> : null; })()}
                  <div className="head-foot">
                    <div className="heatbox" aria-label={`当前热度 ${heatOf(lead)} / 5`}>
                      <span className="heat-cells" aria-hidden="true">
                        {heatCells(heatOf(lead)).map((on, i) => <b key={i} className={on ? 'on' : undefined} />)}
                      </span>
                      <span className="heat-num">{heatOf(lead)}/5</span>
                    </div>
                    {reactionsAvailable && <ReactionButtons item={lead} current={reactionOf(lead.id)} onReact={doReact} />}
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
                          {item.practice_domain && (
                            <span
                              className="ftag"
                              title={interestDomains.includes(item.practice_domain) ? '命中你的兴趣方向, 已优先展示' : '实践域'}
                              style={interestDomains.includes(item.practice_domain)
                                ? { color: 'var(--sn-mint, #00e5a0)', background: 'transparent', border: '1px solid var(--sn-mint, #00e5a0)' }
                                : { color: 'var(--sn-text-dim)', background: 'transparent', border: '1px solid var(--sn-line)' }}
                            >
                              {PRACTICE_DOMAIN_LABELS[item.practice_domain] || item.practice_domain}
                            </span>
                          )}
                          <DeepReadChip id={item.id} itemTitle={item.title} />
                          {reactionsAvailable && <ReactionButtons item={item} current={reactionOf(item.id)} onReact={doReact} />}
                          <StarButton item={item} fav={isFavorite(item.id)} onToggle={star} />
                        </div>
                      </div>
                    </div>
                  ))}
                </section>
              )}

              {/* 快讯流 / 告警视图 (2026-09-27 四模式 P1: alert 接真告警列表, 撤前端假告警) */}
              <section aria-label={mode === 'alert' ? '资讯告警' : '实时快讯'}>
                {mode === 'alert' ? (
                  <NewsAlertList />
                ) : (
                  <>
                    <div className="flash-head">
                      <h2>实时快讯</h2>
                      <span className="flash-count num">
                        PAGE {page} · {items.length} ITEMS
                        {latestIngestionCount ? ` · 最近一轮 +${latestIngestionCount}` : ''}
                        {latestIngestionAt ? ` · ${relTime(latestIngestionAt)}` : ''}
                      </span>
                    </div>
                    <ul className="flash-list">
                      {/* 常规快讯 */}
                      {flashes.map(item => (
                        <FlashRow key={item.id} item={item} interestDomains={interestDomains} fav={isFavorite(item.id)} onStar={star} reaction={reactionOf(item.id)} onReact={doReact} showReactions={reactionsAvailable} />
                      ))}
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
                  </>
                )}
              </section>
            </>
          )}
        </main>

        {/* 右栏 */}
        <aside className="rail">
          <RailWithPipe quality={quality} todos={todos} />
        </aside>
      </div>

      {/* v0.8.5 能力区块: 受管信号 (SK-01 供给, 立项 → /cases/:id) */}
      <SignalPanel />

      {/* 页脚状态行 */}
      <footer className="endnote">
        <span>SECNEWS EDITORIAL DESK · 资料层</span>
        <span>本地运行 · 无云端依赖</span>
        <span>SSE 已连接 · 每 {collectMinutes} 分钟自动采集 · 采集完成即刷新</span>
        <span>{scopeLabel} {total} 篇 · 每页 {pageSize}</span>
      </footer>
    </SentinelShell>
  );
}
