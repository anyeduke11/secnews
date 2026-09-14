/**
 * SentinelShell — 哨兵终端全站共享壳
 *
 * 信息架构核心 (V2 → NAV4 设计稿): 四菜单工作流
 *   资讯 / (采集与浏览) → 知识 /knowledge (沉淀与关联) → 行动 /action (计划与输出) → 设置 /settings (配置与扩展)
 *
 * 职责:
 *  - appbar: 品牌 + 四菜单导航 (active 态) + 主题切换/时钟/设置
 *  - pipeline 心跳条: 采集管道生命体征, 全站常驻 (设计契约:
 *    "32 个源的活/病/死一屏可见" 不只属于首页)
 *  - 子页通过 children 注入; SSE collect 事件由各页自行订阅
 *  - 2026-09-10 壳统一: 工具页 (PageLayout) 也走本壳, layer=null 表示无高亮层,
 *    未传 ingested 时壳自取 24h 收录数 (左侧 AppNav 已删除)
 *  - 2026-09-13 NAV4: 三层→四菜单, layer 语义改为 menu key; menuOf() 判定工具页归属
 */
import { createContext, useCallback, useContext, useEffect, useRef, useState } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import { useTheme } from '../../contexts/ThemeContext';
import { listHotspots } from '../../api/hotspots';
import { getSourceHealth, type SourceHealthPayload } from '../../api/sources';
import { getJSON } from '../../lib/api';
import './sentinel.css';

export type SentinelLayer = 'data' | 'judge' | 'action' | 'knowledge' | 'settings';

/** 心跳条数据 — shell 拉一次, 供子页复用 (管道口径统一) */
export interface PipeSnapshot {
  active: number;
  stale: number;
  dead: number;
  total: number;
  health: '良好' | '一般' | '告警' | '--';
  sources: SourceHealthRow[];
  /** /api/kl/pipeline/stats — 生命周期漏斗 (旧 workbench StatusBar 常驻项) */
  funnel: { stage: string; count: number }[] | null;
  /** 队列三态; error > 0 时以 amber 提示 */
  queue: { pending: number; running: number; error: number } | null;
}

/** /api/sources/health 单行 — 右栏源监控还需累计产出与最近活动时间 */
export interface SourceHealthRow {
  category: string;
  source_name: string;
  status: string;
  total_items?: number;
  last_seen_at?: string | null;
}

interface PipelineStats {
  funnel?: { stage: string; count: number }[];
  queue?: { pending?: number; running?: number; error?: number };
}

async function fetchPipelineStats(): Promise<Pick<PipeSnapshot, 'funnel' | 'queue'>> {
  try {
    // apiFetch 非 ok / 网络失败抛错 → 降级为 null, 不影响源健康展示
    const data = await getJSON<PipelineStats>('/api/kl/pipeline/stats');
    return {
      funnel: Array.isArray(data.funnel) ? data.funnel : null,
      queue: data.queue
        ? { pending: data.queue.pending ?? 0, running: data.queue.running ?? 0, error: data.queue.error ?? 0 }
        : null,
    };
  } catch {
    // 端点未注册或后端不可达时降级为 null, 不影响源健康展示
    return { funnel: null, queue: null };
  }
}

function clockText(d: Date): string {
  const p = (n: number) => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} · ${p(d.getHours())}:${p(d.getMinutes())}`;
}

/** 今日收录兜底口径 (与 SentinelGraphPage / SentinelGardenPage 同源): 只取 24h total */
async function fetchIngested24h(): Promise<number | null> {
  try {
    const data = await listHotspots({ category: 'all', time_range: '24h', limit: 1 });
    return typeof data.total === 'number' ? data.total : null;
  } catch {
    return null;
  }
}

export async function fetchPipe(): Promise<PipeSnapshot> {
  const [res, stats] = await Promise.all([
    // apiFetch 非 ok / 网络失败抛错 → null (对应原 r.ok 分支检查 + .catch(() => null))
    getSourceHealth()
      .then(row => row as SourceHealthPayload & {
        sources?: SourceHealthRow[];
        registered_total: number;
        registered_active: number;
        registered_stale: number;
        registered_dead: number;
      })
      .catch(() => null),
    fetchPipelineStats(),
  ]);
  const rows: SourceHealthRow[] = res?.sources || [];
  // 优先用后端"注册且启用"口径: source_stats 历史行含已无 collector 抓取的孤儿源
  // (旧分母 152 含 22 个孤儿行, 若干还显示 active), 拿它当分母会让"源在线 x/y"
  // 与管道状态一起失真。后端未升级缺字段时回落逐行统计, 保持兼容。
  const registered = typeof res?.registered_total === 'number' ? res : null;
  const active = registered ? registered.registered_active : rows.filter(s => s.status === 'active').length;
  const stale = registered ? registered.registered_stale : rows.filter(s => s.status === 'stale').length;
  const dead = registered ? registered.registered_dead : rows.filter(s => s.status === 'dead').length;
  const total = registered ? registered.registered_total : rows.length;
  const ratio = total > 0 ? active / total : 0;
  return {
    active, stale, dead, total, sources: rows, ...stats,
    health: total === 0 ? '--' : ratio >= 0.9 ? '良好' : ratio >= 0.7 ? '一般' : '告警',
  };
}

const PipeContext = createContext<{ pipe: PipeSnapshot | null; reload: () => void }>({
  pipe: null,
  reload: () => {},
});

/** 已挂载壳的 reload 登记 — 三层页是「页面渲染壳」结构, 页面组件体内的 hook 永远在 Provider 之外,
 *  经 context 只能拿到默认 no-op (2026-09-10 前 SSE 事件从未真正刷新过心跳条); usePipeReloadOnSse 优先走这里 */
let mountedReload: (() => void) | null = null;

/** 子页消费心跳数据 (避免重复拉取 /api/sources/health); 注意 pipe 只在壳的子树内可读 */
export function usePipe() {
  return useContext(PipeContext);
}

/** NAV4 (2026-09-13): 四菜单壳 — 资讯 / 知识 / 行动 / 设置
 *  - 资讯 → / (情报流 + 质量区 + 深读 + 历史)
 *  - 知识 → /knowledge (知识库 + 图谱 + 能力资产 + 加工工具 + 复习)
 *  - 行动 → /action (今日行动 + 案件队列 + 待办 + 报告 + 泳道)
 *  - 设置 → /settings (17 配置 + 密钥/同步/技能库配置 + 扩展域)
 *  守卫 = routes/__tests__/nav4_shell.test.tsx
 */
const LAYER_DEFS: { layer: SentinelLayer; label: string; sub: string; to: string; icon: JSX.Element }[] = [
  {
    layer: 'data', label: '资讯', sub: '看什么 — 情报流、质量筛选、采集管道', to: '/',
    icon: <svg width="13" height="13" viewBox="0 0 13 13" fill="none" aria-hidden="true"><rect x="1.5" y="1.5" width="10" height="10" rx="1.5" stroke="currentColor" strokeWidth="1.5" /><path d="M4.5 4.5h4M4.5 7h4M4.5 9.5h2" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round" /></svg>,
  },
  {
    layer: 'knowledge', label: '知识', sub: '沉淀什么 — 知识库、图谱、能力资产', to: '/knowledge',
    icon: <svg width="13" height="13" viewBox="0 0 13 13" fill="none" aria-hidden="true"><circle cx="6.5" cy="6.5" r="5" stroke="currentColor" strokeWidth="1.5" /><path d="M6.5 4v4M4.5 6.5h4" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round" /></svg>,
  },
  {
    layer: 'action', label: '行动', sub: '做什么 — 案件、待办、今日行动、产出', to: '/action',
    icon: <svg width="13" height="13" viewBox="0 0 13 13" fill="none" aria-hidden="true"><path d="M2 7l3 3L11 2.5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" /><path d="M7.5 11h3.5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" /></svg>,
  },
  {
    layer: 'settings', label: '设置', sub: '怎么配 — 全局配置、密钥、同步、扩展域', to: '/settings',
    icon: <svg width="13" height="13" viewBox="0 0 13 13" fill="none" aria-hidden="true"><circle cx="6.5" cy="6.5" r="2.2" stroke="currentColor" strokeWidth="1.5" /><path d="M6.5 1.8v2M6.5 9.2v2M1.8 6.5h2M9.2 6.5h2M3.7 3.7l1.4 1.4M8.9 8.9l1.4 1.4M9.3 3.7l-1.4 1.4M4.1 8.9l-1.4 1.4" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round" /></svg>,
  },
];

/**
 * 路径 → 菜单归属 (NAV4: 四菜单壳 active 态判定).
 * 优先级: 精确匹配 > 前缀匹配; 未命中返回 null.
 */
export function menuOf(pathname: string): SentinelLayer | null {
  // 精确匹配 / action / knowledge / settings → 直接归属
  if (pathname === '/' || pathname.startsWith('/judge') || pathname.startsWith('/cases')) return 'data';
  if (pathname.startsWith('/knowledge') || pathname.startsWith('/deep') || pathname.startsWith('/reviews')) return 'knowledge';
  if (pathname.startsWith('/action') || pathname.startsWith('/garden')) return 'action';
  if (pathname.startsWith('/settings') || pathname.startsWith('/secrets') || pathname.startsWith('/sync') || pathname.startsWith('/skills') || pathname.startsWith('/codegarden') || pathname.startsWith('/maint')) return 'settings';
  // 工具页按语义归属
  if (pathname.startsWith('/report') || pathname.startsWith('/todos')) return 'action';
  if (pathname.startsWith('/tags') || pathname.startsWith('/extract') || pathname.startsWith('/search') || pathname.startsWith('/dashboard') || pathname.startsWith('/skill-store')) return 'knowledge';
  if (pathname.startsWith('/quality') || pathname.startsWith('/history')) return 'data';
  if (pathname.startsWith('/secnews')) {
    // secnews 子视图按内容归属: feed/pipeline/analytics→data, knowledge→knowledge, analyze→action, observability→settings
    const sub = pathname.replace(/^\/secnews\/?/, '') || 'feed';
    if (sub === 'feed' || sub === 'pipeline' || sub === 'analytics') return 'data';
    if (sub === 'knowledge') return 'knowledge';
    if (sub === 'analyze') return 'action';
    if (sub === 'observability') return 'settings';
    return 'data'; // 默认归资讯
  }
  return null;
}

export function SentinelShell({ layer, mode = 'brief', ingested, children }: {
  /** 四菜单高亮; null = 工具页 (由 menuOf(pathname) 自动推断归属) */
  layer: SentinelLayer | null;
  mode?: string;
  /** 今日收录: 页面自算则传值 (null = 该页无此口径显示 …); 不传则壳自取 24h total */
  ingested?: number | null;
  children: React.ReactNode;
}) {
  const navigate = useNavigate();
  const { theme, cycleTheme } = useTheme();
  const { pathname } = useLocation();

  const [pipe, setPipe] = useState<PipeSnapshot | null>(null);
  const [clock, setClock] = useState(() => clockText(new Date()));
  const [selfIngested, setSelfIngested] = useState<number | null>(null);
  const shownIngested = ingested === undefined ? selfIngested : ingested;

  // 菜单 active 态: 优先用显式 layer, 否则按路径推断 (tool 页自动高亮归属菜单)
  const activeLayer = layer ?? menuOf(pathname);

  const reload = useCallback(() => { fetchPipe().then(setPipe); }, []);

  useEffect(() => { reload(); }, [reload]);
  useEffect(() => {
    mountedReload = reload;
    return () => { if (mountedReload === reload) mountedReload = null; };
  }, [reload]);
  useEffect(() => {
    if (ingested !== undefined) return;
    let alive = true;
    fetchIngested24h().then(n => { if (alive) setSelfIngested(n); });
    return () => { alive = false; };
  }, [ingested]);
  useEffect(() => {
    const t = setInterval(() => setClock(clockText(new Date())), 30000);
    return () => clearInterval(t);
  }, []);

  return (
    <PipeContext.Provider value={{ pipe, reload }}>
      <div className="sentinel" data-mode={mode}>
        {/* ===== 顶栏: 四菜单导航 ===== */}
        <header className="appbar">
          <a className="brand" href="/" onClick={e => { e.preventDefault(); navigate('/'); }}>
            <span className="brand-mark" aria-hidden="true">
              <svg width="12" height="12" viewBox="0 0 12 12" fill="none"><path d="M2 6.5l2.5 2.5L10 3" stroke="var(--sn-mint)" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" /></svg>
            </span>
            SecNews <small>SECURITY INTEL STATION</small>
          </a>

          <nav className="layers" aria-label="四菜单导航">
            {LAYER_DEFS.map((def, i) => (
              <span key={def.layer} style={{ display: 'contents' }}>
                {i > 0 && (
                  <span className="layer-flow" aria-hidden="true">
                    <svg width="12" height="12" viewBox="0 0 12 12" fill="none"><path d="M2.5 6h6M6 3.5L8.5 6 6 8.5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" /></svg>
                  </span>
                )}
                <a
                  className={`layer-link${activeLayer === def.layer ? ' active' : ''}`}
                  href={def.to}
                  aria-current={activeLayer === def.layer ? 'page' : undefined}
                  onClick={e => { e.preventDefault(); navigate(def.to); }}
                >
                  <b>{def.icon}{def.label}</b>
                  <span>{def.sub}</span>
                </a>
              </span>
            ))}
          </nav>

          <div className="appbar-right">
            <button type="button" className="iconbtn" onClick={cycleTheme} aria-label={theme === 'dark' ? '切换到晨间亮色' : theme === 'paper' ? '切换到夜航暗色' : '切换到纸面版'}>
              <svg className="tb-sun" viewBox="0 0 18 18" width="17" height="17" aria-hidden="true" focusable="false"><circle cx="9" cy="9" r="3.6" fill="none" stroke="currentColor" strokeWidth="1.5" /><path d="M9 1.2v2.1M9 14.7v2.1M1.2 9h2.1M14.7 9h2.1M3.7 3.7l1.5 1.5M12.8 12.8l1.5 1.5M14.3 3.7l-1.5 1.5M5.2 12.8l-1.5 1.5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" /></svg>
              <svg className="tb-moon" viewBox="0 0 18 18" width="17" height="17" aria-hidden="true" focusable="false"><path d="M15.2 11.2A6.6 6.6 0 0 1 6.8 2.8a6.6 6.6 0 1 0 8.4 8.4Z" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinejoin="round" /></svg>
              <svg className="tb-paper" viewBox="0 0 18 18" width="17" height="17" aria-hidden="true" focusable="false"><rect x="3.5" y="2.5" width="11" height="13" rx="1.5" fill="none" stroke="currentColor" strokeWidth="1.5" /><path d="M5.5 5.5h7M5.5 8.5h7M5.5 11.5h4" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round" /></svg>
            </button>
            <span className="clock num">{clock}</span>
            <button className="iconbtn" aria-label="设置" onClick={() => navigate('/settings')}>
              <svg width="17" height="17" viewBox="0 0 17 17" fill="none"><circle cx="8.5" cy="8.5" r="2.2" stroke="currentColor" strokeWidth="1.5" /><path d="M8.5 1.8v2M8.5 13.2v2M1.8 8.5h2M13.2 8.5h2M3.7 3.7l1.4 1.4M11.9 11.9l1.4 1.4M13.3 3.7l-1.4 1.4M5.1 11.9l-1.4 1.4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" /></svg>
            </button>
          </div>
        </header>

        {/* ===== 管道心跳条: 全站常驻 ===== */}
        <section className="pipeline" aria-label="采集管道状态">
          <div className="pipe-block">
            <span className="pipe-k">管道状态</span>
            <span className="pipe-v" style={{ color: pipe?.health === '良好' ? 'var(--sn-mint)' : pipe?.health === '--' ? undefined : pipe?.health === '一般' ? 'var(--sn-amber)' : 'var(--sn-red)' }}>
              {pipe?.health ?? '…'}
            </span>
          </div>
          <div className="pipe-block">
            <span className="pipe-k" title="分母 = 采集器注册表中 enabled=1 的源数（不含已停止抓取的 source_stats 历史行）">源在线</span>
            <span className="pipe-v">
              {pipe ? `${pipe.active} / ${pipe.total}` : '…'}
              {pipe && pipe.stale > 0 && <span className="delta" style={{ color: 'var(--sn-amber)' }}>{pipe.stale} 重试</span>}
              {pipe && pipe.dead > 0 && <span className="delta" style={{ color: 'var(--sn-red)' }}>{pipe.dead} 离线</span>}
            </span>
          </div>
          <div className="pipe-block">
            <span className="pipe-k">今日收录</span>
            <span className="pipe-v">{shownIngested != null ? `${shownIngested} 篇` : '…'}</span>
          </div>
          <div className="pipe-block">
            <span className="pipe-k" title="统计对象 = wiki md frontmatter（llm-wiki-2.0 归档）；管线推进实际读写 DB knowledge_items.lifecycle，两者数字本就不同">管线漏斗</span>
            <span className="pipe-v pipe-funnel">
              {pipe?.funnel
                ? pipe.funnel.map(f => (
                  <span className="fs" key={f.stage}>
                    <i>{f.stage.replace(/^kl:/, '')}</i>
                    <b className="num">{f.count}</b>
                  </span>
                ))
                : '…'}
            </span>
          </div>
          <div className="pipe-block">
            <span className="pipe-k">队列</span>
            <span className="pipe-v">
              {pipe?.queue
                ? <>
                  {pipe.queue.pending} 待 · {pipe.queue.running} 运
                  {pipe.queue.error > 0 && (
                    <span className="delta" style={{ color: 'var(--sn-amber)' }}>{pipe.queue.error} 异常</span>
                  )}
                </>
                : '…'}
            </span>
          </div>
          <div className="pipe-live">
            <div className="beat-row">
              <span className="pulse" aria-hidden="true" />
              <span className="beat-label">PIPELINE LIVE</span>
            </div>
            <div className="beat-lights" role="img" aria-label={pipe ? `${pipe.total} 个采集源: ${pipe.active} 正常, ${pipe.stale} 重试中, ${pipe.dead} 离线` : '加载中'}>
              {pipe?.sources.slice(0, 40).map((s, idx) => (
                <i key={`${s.category}-${s.source_name}-${idx}`} className={s.status === 'stale' ? 'warm' : s.status === 'dead' ? 'dead' : undefined} />
              ))}
            </div>
          </div>
        </section>

        {children}
      </div>
    </PipeContext.Provider>
  );
}

/** 心跳条节流刷新 hook — 由各页的 useRealtimeInvalidation (src/hooks/realtime.ts) handler
 *  在 SSE 事件到达时调用。本 hook 本身不订阅 SSE (迁移后也不是 useSSE 消费方), 只提供
 *  10s 节流 + mountedReload 优先于 context reload 的 DEV-0167 语义, 迁移时逐字保留 */
export function usePipeReloadOnSse() {
  const { reload } = usePipe();
  const lastRef = useRef(0);
  return useCallback(() => {
    const now = Date.now();
    if (now - lastRef.current < 10000) return;
    lastRef.current = now;
    (mountedReload ?? reload)();
  }, [reload]);
}
