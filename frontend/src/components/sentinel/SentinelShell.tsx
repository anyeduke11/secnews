/**
 * SentinelShell — 哨兵终端全站共享壳
 *
 * 信息架构核心 (V2 设计稿): 三层工作流
 *   资料层 / (采集与浏览) → 判断层 /judge (筛选与关联) → 行动层 /action (计划与输出)
 *
 * 职责:
 *  - appbar: 品牌 + 三层导航 (active 态) + 主题切换/时钟/设置
 *  - pipeline 心跳条: 采集管道生命体征, 全站常驻 (设计契约:
 *    "32 个源的活/病/死一屏可见" 不只属于首页)
 *  - 子页通过 children 注入; SSE collect 事件由各页自行订阅
 */
import { createContext, useCallback, useContext, useEffect, useRef, useState } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { useTheme } from '../../contexts/ThemeContext';
import './sentinel.css';

export type SentinelLayer = 'data' | 'judge' | 'action';

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
    const r = await fetch('/api/kl/pipeline/stats', { headers: { Accept: 'application/json' } });
    if (!r.ok) return { funnel: null, queue: null };
    const data = (await r.json()) as PipelineStats;
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

export async function fetchPipe(): Promise<PipeSnapshot> {
  const [res, stats] = await Promise.all([
    fetch('/api/sources/health', { headers: { Accept: 'application/json' } })
      .then(r => (r.ok ? r.json() : null)).catch(() => null),
    fetchPipelineStats(),
  ]);
  const rows: SourceHealthRow[] = (res && res.sources) || [];
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

/** 子页消费心跳数据 (避免重复拉取 /api/sources/health) */
export function usePipe() {
  return useContext(PipeContext);
}

const LAYER_DEFS: { layer: SentinelLayer; label: string; sub: string; to: string; icon: JSX.Element }[] = [
  {
    layer: 'data', label: '资料层', sub: '信息采集与组织', to: '/',
    icon: <svg width="13" height="13" viewBox="0 0 13 13" fill="none" aria-hidden="true"><rect x="1.5" y="7.5" width="4" height="4" rx="1" stroke="currentColor" strokeWidth="1.5" /><rect x="7.5" y="1.5" width="4" height="4" rx="1" stroke="currentColor" strokeWidth="1.5" /></svg>,
  },
  {
    layer: 'judge', label: '判断层', sub: '筛选、分析、关联', to: '/judge',
    icon: <svg width="13" height="13" viewBox="0 0 13 13" fill="none" aria-hidden="true"><circle cx="5.5" cy="5.5" r="3.5" stroke="currentColor" strokeWidth="1.5" /><path d="M8.2 8.2L11 11" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" /></svg>,
  },
  {
    layer: 'action', label: '行动层', sub: '计划、学习、创作', to: '/action',
    icon: <svg width="13" height="13" viewBox="0 0 13 13" fill="none" aria-hidden="true"><path d="M2 7l3 3L11 2.5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" /><path d="M7.5 11h3.5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" /></svg>,
  },
];

/** 报纸版删除后, 这些能力失去了唯一点击入口 — 由壳层溢出菜单统一承接 */
const UTILITY_GROUPS: { label: string; items: { to: string; label: string; note: string }[] }[] = [
  {
    label: '情报输出',
    items: [
      { to: '/report', label: '周报 / 月报', note: 'REPORT' },
      { to: '/search', label: '统一搜索', note: 'FIND' },
      { to: '/bid-alert', label: '标书提醒', note: 'BID' },
      { to: '/history', label: '浏览历史', note: 'HISTORY' },
      { to: '/reviews', label: '间隔复习', note: 'SRS' },
      { to: '/secnews', label: 'SecNews 看板', note: 'BOARD' },
    ],
  },
  {
    label: '知识资产',
    items: [
      { to: '/knowledge', label: '知识库', note: 'KNOWLEDGE' },
      { to: '/tags', label: '标签管理', note: 'TAGS' },
      { to: '/extract', label: '自动提取', note: 'EXT' },
      { to: '/skills', label: '技能库', note: 'SKILLS' },
      { to: '/todos', label: '待办', note: 'TODOS' },
    ],
  },
  {
    label: '运维与配置',
    items: [
      { to: '/garden', label: 'CodeGarden', note: 'GARDEN' },
      { to: '/secrets', label: '密钥管理', note: 'SECRETS' },
      { to: '/sync', label: '同步与备份', note: 'SYNC' },
      { to: '/settings', label: '全局设置', note: 'SETTINGS' },
    ],
  },
];

function SentinelMoreMenu() {
  const [open, setOpen] = useState(false);
  const boxRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const onDown = (e: MouseEvent) => {
      if (boxRef.current && !boxRef.current.contains(e.target as Node)) setOpen(false);
    };
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') setOpen(false); };
    document.addEventListener('mousedown', onDown);
    document.addEventListener('keydown', onKey);
    return () => {
      document.removeEventListener('mousedown', onDown);
      document.removeEventListener('keydown', onKey);
    };
  }, [open]);

  return (
    <div className="sn-more" ref={boxRef}>
      <button
        type="button"
        className="iconbtn sn-more-btn"
        aria-haspopup="menu"
        aria-expanded={open}
        onClick={() => setOpen(o => !o)}
      >
        更多
        <svg width="9" height="9" viewBox="0 0 9 9" aria-hidden="true"><path d="M1.5 3l3 3 3-3" fill="none" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" /></svg>
      </button>
      {open && (
        <div className="sn-menu" role="menu" aria-label="功能入口">
          {UTILITY_GROUPS.map(g => (
            <div className="sn-menu-grp" key={g.label}>
              <p className="sn-menu-kick num">{g.label}</p>
              {g.items.map(it => (
                <Link key={it.to} className="sn-menu-item" role="menuitem" to={it.to} onClick={() => setOpen(false)}>
                  <span>{it.label}</span>
                  <span className="sn-menu-note num">{it.note}</span>
                </Link>
              ))}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

export function SentinelShell({ layer, mode = 'brief', ingested, children }: {
  layer: SentinelLayer;
  mode?: string;
  ingested?: number | null;
  children: React.ReactNode;
}) {
  const navigate = useNavigate();
  const { theme, toggleTheme } = useTheme();

  const [pipe, setPipe] = useState<PipeSnapshot | null>(null);
  const [clock, setClock] = useState(() => clockText(new Date()));

  const reload = useCallback(() => { fetchPipe().then(setPipe); }, []);

  useEffect(() => { reload(); }, [reload]);
  useEffect(() => {
    const t = setInterval(() => setClock(clockText(new Date())), 30000);
    return () => clearInterval(t);
  }, []);

  return (
    <PipeContext.Provider value={{ pipe, reload }}>
      <div className="sentinel" data-mode={mode}>
        {/* ===== 顶栏: 三层工作流导航 ===== */}
        <header className="appbar">
          <a className="brand" href="/" onClick={e => { e.preventDefault(); navigate('/'); }}>
            <span className="brand-mark" aria-hidden="true">
              <svg width="12" height="12" viewBox="0 0 12 12" fill="none"><path d="M2 6.5l2.5 2.5L10 3" stroke="var(--sn-mint)" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" /></svg>
            </span>
            SecNews <small>SECURITY INTEL STATION</small>
          </a>

          <nav className="layers" aria-label="三层工作流导航">
            {LAYER_DEFS.map((def, i) => (
              <span key={def.layer} style={{ display: 'contents' }}>
                {i > 0 && (
                  <span className="layer-flow" aria-hidden="true">
                    <svg width="12" height="12" viewBox="0 0 12 12" fill="none"><path d="M2.5 6h6M6 3.5L8.5 6 6 8.5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" /></svg>
                  </span>
                )}
                <a
                  className={`layer-link${layer === def.layer ? ' active' : ''}`}
                  href={def.to}
                  aria-current={layer === def.layer ? 'page' : undefined}
                  onClick={e => { e.preventDefault(); navigate(def.to); }}
                >
                  <b>{def.icon}{def.label}</b>
                  <span>{def.sub}</span>
                </a>
              </span>
            ))}
          </nav>

          <div className="appbar-right">
            <SentinelMoreMenu />
            <button type="button" className="iconbtn" onClick={toggleTheme} aria-label={theme === 'dark' ? '切换到晨间亮色' : '切换到夜航暗色'}>
              <svg className="tb-sun" viewBox="0 0 18 18" width="17" height="17" aria-hidden="true" focusable="false"><circle cx="9" cy="9" r="3.6" fill="none" stroke="currentColor" strokeWidth="1.5" /><path d="M9 1.2v2.1M9 14.7v2.1M1.2 9h2.1M14.7 9h2.1M3.7 3.7l1.5 1.5M12.8 12.8l1.5 1.5M14.3 3.7l-1.5 1.5M5.2 12.8l-1.5 1.5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" /></svg>
              <svg className="tb-moon" viewBox="0 0 18 18" width="17" height="17" aria-hidden="true" focusable="false"><path d="M15.2 11.2A6.6 6.6 0 0 1 6.8 2.8a6.6 6.6 0 1 0 8.4 8.4Z" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinejoin="round" /></svg>
            </button>
            <span className="clock num">{clock}</span>
            <button className="iconbtn" aria-label="设置" onClick={() => navigate('/sentinel/settings')}>
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
            <span className="pipe-k">源在线</span>
            <span className="pipe-v">
              {pipe ? `${pipe.active} / ${pipe.total}` : '…'}
              {pipe && pipe.stale > 0 && <span className="delta" style={{ color: 'var(--sn-amber)' }}>{pipe.stale} 重试</span>}
              {pipe && pipe.dead > 0 && <span className="delta" style={{ color: 'var(--sn-red)' }}>{pipe.dead} 离线</span>}
            </span>
          </div>
          <div className="pipe-block">
            <span className="pipe-k">今日收录</span>
            <span className="pipe-v">{ingested != null ? `${ingested} 篇` : '…'}</span>
          </div>
          <div className="pipe-block">
            <span className="pipe-k">管线漏斗</span>
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

/** 心跳条节流刷新 hook (子页 SSE 事件驱动时复用) */
export function usePipeReloadOnSse() {
  const { reload } = usePipe();
  const lastRef = useRef(0);
  return useCallback(() => {
    const now = Date.now();
    if (now - lastRef.current < 10000) return;
    lastRef.current = now;
    reload();
  }, [reload]);
}
