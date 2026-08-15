/**
 * Header — 报头 (v2)
 *
 * Phase 5: 设计治理
 * - 移除冗余 NAV_LINKS（旧路由已纳入三层架构子导航）
 * - LayerNav 提升至日期行，作为主导航
 * - 布局简化: 首行 日期+层导航 | 次行 报头+操作按钮
 */
import React, { useEffect, useState, MutableRefObject } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import { CatchupButton } from './CatchupButton';
import { LayerNav } from './LayerNav';
import { useLayerSubNav, DATA_SUB_NAV, JUDGE_SUB_NAV, ACTION_SUB_NAV, FLOW_COLORS } from './layout/LayerHeader';

interface HeaderProps {
  latestIngestionCount: number;
  latestIngestionAt?: string | null;
  lastUpdated: string | null;
  onRefresh: () => void;
  theme: 'dark' | 'light';
  onThemeToggle: () => void;
  onOpenFavorites?: () => void;
  favoritesCount?: number;
  refreshIntervalMinutes?: number;
  lastAutoRefreshAtRef?: MutableRefObject<number>;
  todosOpenCount?: number;
  refreshing?: boolean;
  /** 管线各层数据量（可选） */
  pipelineSummary?: { data: number; judge: number; action: number };
  /** 当前层名称（三层架构标题行） */
  layerName?: string;
  /** 当前层副标题 */
  layerSubtitle?: string;
}

function pad2(n: number): string { return n < 10 ? `0${n}` : `${n}`; }
function formatClock(d: Date): string { return `${pad2(d.getHours())}:${pad2(d.getMinutes())}`; }
function formatCountdown(ms: number, intervalMinutes: number): string {
  const total = Math.max(0, Math.floor(ms / 1000));
  const m = Math.floor(total / 60);
  const s = total % 60;
  if (intervalMinutes >= 720) {
    const h = Math.floor(total / 3600);
    return `${pad2(h)}:${pad2(m)}:${pad2(s)}`;
  }
  return `${pad2(m)}:${pad2(s)}`;
}

const WEEKDAYS = ['日', '一', '二', '三', '四', '五', '六'];
function formatDateLine(d: Date): string {
  return `${d.getFullYear()}年${d.getMonth() + 1}月${d.getDate()}日 星期${WEEKDAYS[d.getDay()]}`;
}

function Icon({ children, size = 14 }: { children: React.ReactNode; size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      {children}
    </svg>
  );
}

export function Header({
  latestIngestionCount, lastUpdated, onRefresh, theme, onThemeToggle,
  onOpenFavorites, favoritesCount = 0, refreshIntervalMinutes,
  lastAutoRefreshAtRef, todosOpenCount = 0, refreshing = false,
  pipelineSummary, layerName, layerSubtitle,
}: HeaderProps) {
  const navigate = useNavigate();
  const location = useLocation();
  const [now, setNow] = useState<number>(Date.now());
  const [secretTTL, setSecretTTL] = useState<number | null>(null);
  // P0-4: "更多"菜单 — 承接旧 Sidebar 中被孤立的页面入口
  // (知识管理 / Skill / 密钥 / 同步), 消除"路由存在但主导航不可达"。
  const [moreOpen, setMoreOpen] = useState(false);
  const moreRef = React.useRef<HTMLDivElement>(null);

  useEffect(() => {
    const onDocClick = (e: MouseEvent) => {
      if (moreRef.current && !moreRef.current.contains(e.target as Node)) {
        setMoreOpen(false);
      }
    };
    document.addEventListener('mousedown', onDocClick);
    return () => document.removeEventListener('mousedown', onDocClick);
  }, []);

  const MORE_ITEMS = [
    { path: '/knowledge', label: '知识管理', hint: '4 大领域 + 6 认知模式' },
    { path: '/skills', label: 'Skill 管理', hint: '技能配置' },
    { path: '/secrets', label: '密钥管理', hint: 'LLM API 密钥' },
    { path: '/sync', label: '跨端同步', hint: 'WebDAV 同步' },
  ];

  useEffect(() => {
    const timer = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, []);

  useEffect(() => {
    let cancelled = false;
    const poll = async () => {
      try {
        const r = await fetch('/api/secrets/status');
        if (!cancelled && r.ok) {
          const data = await r.json();
          setSecretTTL(data.setup && data.unlocked ? data.remaining_seconds : null);
        }
      } catch {}
    };
    poll();
    const t = window.setInterval(poll, 15000);
    return () => { cancelled = true; window.clearInterval(t); };
  }, []);

  const intervalMinutes = refreshIntervalMinutes ?? 30;
  const intervalMs = Math.max(intervalMinutes, 1) * 60 * 1000;
  const lastTick = lastAutoRefreshAtRef?.current ?? now;
  const remainingMs = lastTick + intervalMs - now;
  const lastUpdatedClock = lastUpdated ? formatClock(new Date(lastUpdated)) : '--:--';
  const countdownText = remainingMs > 0 ? formatCountdown(remainingMs, intervalMinutes) : '00:00';
  const dateLine = formatDateLine(new Date(now));

  // 根据当前路由确定子导航配置
  const pathname = location.pathname;
  let subNavItems: { key: string; label: string; path: string }[] = [];
  let subNavBasePath = '';
  if (pathname.startsWith('/data')) {
    subNavItems = DATA_SUB_NAV;
    subNavBasePath = '/data';
  } else if (pathname.startsWith('/judge') || pathname.startsWith('/quality') || pathname.startsWith('/knowledge')) {
    subNavItems = JUDGE_SUB_NAV;
    subNavBasePath = '/judge';
  } else if (pathname.startsWith('/action')) {
    subNavItems = ACTION_SUB_NAV;
    subNavBasePath = '/action';
  }
  const subNav = useLayerSubNav(subNavBasePath, subNavItems, pathname);

  // 层标题行颜色（从路径推断当前层）
  const currentLayerKey = pathname.startsWith('/judge') ? 'judge'
    : pathname.startsWith('/action') ? 'action'
    : 'data';
  const layerColor = FLOW_COLORS[currentLayerKey] || 'var(--accent)';

  const actionButtons = (
    <>
      <button onClick={onOpenFavorites} className="nav-btn relative" title={`收藏${favoritesCount > 0 ? ` (${favoritesCount})` : ''}`} aria-label={`打开收藏列表${favoritesCount > 0 ? `, 共 ${favoritesCount} 条` : ''}`}>
        <Icon size={14}><polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2" /></Icon>
        {favoritesCount > 0 && (
          <span className="absolute -top-0.5 -right-0.5 min-w-[15px] h-[15px] px-[3px] rounded-full text-[10px] font-bold flex items-center justify-center" style={{ backgroundColor: 'var(--accent)', color: 'var(--text-on-light)' }}>
            {favoritesCount > 99 ? '99+' : favoritesCount}
          </span>
        )}
      </button>
      {/* P0-4: "更多"菜单 — 知识/Skill/密钥/同步入口 (承接旧 Sidebar) */}
      <div className="relative" ref={moreRef}>
        <button
          onClick={() => setMoreOpen(o => !o)}
          className={`nav-btn ${moreOpen ? 'nav-btn-active' : ''}`}
          title="更多功能"
          aria-label="更多功能"
          aria-expanded={moreOpen}
        >
          <Icon size={14}><circle cx="12" cy="12" r="1" /><circle cx="19" cy="12" r="1" /><circle cx="5" cy="12" r="1" /></Icon>
        </button>
        {moreOpen && (
          <div
            className="absolute right-0 top-full mt-1 z-50 min-w-[180px] rounded-md border bg-[var(--bg-card)] shadow-lg"
            style={{ borderColor: 'var(--border-color)', backgroundColor: 'var(--bg-card)' }}
            role="menu"
          >
            {MORE_ITEMS.map(item => (
              <button
                key={item.path}
                type="button"
                role="menuitem"
                onClick={() => { navigate(item.path); setMoreOpen(false); }}
                className="block w-full text-left px-3 py-2 text-[12px] hover:bg-[var(--bg-hover)]"
                style={{ color: 'var(--text-primary)' }}
              >
                <span className="font-medium">{item.label}</span>
                <span className="block text-[10px]" style={{ color: 'var(--text-muted)' }}>{item.hint}</span>
              </button>
            ))}
          </div>
        )}
      </div>
      <button onClick={() => navigate('/settings')} className="nav-btn" title="设置" aria-label="打开设置">
        <Icon size={14}><circle cx="12" cy="12" r="3" /><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z" /></Icon>
      </button>
      <button onClick={onThemeToggle} className="nav-btn" title={theme === 'dark' ? '切换日报版' : '切换夜读版'} aria-label={theme === 'dark' ? '切换日报版 (浅色主题)' : '切换夜读版 (深色主题)'}>
        {theme === 'dark' ? (
          <Icon size={14}><circle cx="12" cy="12" r="5" /><line x1="12" y1="1" x2="12" y2="3" /><line x1="12" y1="21" x2="12" y2="23" /><line x1="4.22" y1="4.22" x2="5.64" y2="5.64" /><line x1="18.36" y1="18.36" x2="19.78" y2="19.78" /><line x1="1" y1="12" x2="3" y2="12" /><line x1="21" y1="12" x2="23" y2="12" /><line x1="4.22" y1="19.78" x2="5.64" y2="18.36" /><line x1="18.36" y1="5.64" x2="19.78" y2="4.22" /></Icon>
        ) : (
          <Icon size={14}><path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z" /></Icon>
        )}
      </button>
      <CatchupButton />
      <button
        onClick={onRefresh} disabled={refreshing}
        className="nav-btn"
        style={{
          color: refreshing ? 'var(--text-muted)' : 'var(--accent)',
          cursor: refreshing ? 'wait' : 'pointer',
        }}
        title={refreshing ? '正在刷新...' : '刷新数据'}
        aria-label={refreshing ? '刷新中' : '刷新'}
      >
        {refreshing ? (
          <span className="animate-spin-slow flex" aria-hidden="true">
            <Icon size={14}><path d="M21 12a9 9 0 1 1-6.219-8.56" /></Icon>
          </span>
        ) : (
          <Icon size={14}><polyline points="23 4 23 10 17 10" /><polyline points="1 20 1 14 7 14" /><path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15" /></Icon>
        )}
      </button>
    </>
  );

  return (
    <header className="mb-4" style={{ borderBottom: '2px solid var(--text-primary)' }}>
      {/* ── 首行: 日期/状态（靠右） ── */}
      <div
        className="flex items-center justify-end flex-wrap gap-x-2.5 gap-y-1 text-[11.5px]"
        style={{ color: 'var(--text-muted)' }}
      >
        <span className="whitespace-nowrap hidden sm:inline">{dateLine}</span>
        <span className="hidden sm:inline" aria-hidden="true" style={{ color: 'var(--border-color)' }}>|</span>
        <span className="flex items-center gap-1.5 whitespace-nowrap" title="最近摄取更新条数">
          <span className="pulse-dot" style={{ backgroundColor: 'var(--color-general)', width: 5, height: 5, borderRadius: '50%', display: 'inline-block' }} />
          <span className="font-mono tabular-nums font-semibold" style={{ color: 'var(--text-secondary)' }}>{latestIngestionCount}</span>
          <span>更新</span>
        </span>
        <span aria-hidden="true" style={{ color: 'var(--border-color)' }}>|</span>
        <span className="font-mono tabular-nums whitespace-nowrap" title="最近更新时间">{lastUpdatedClock}</span>
        <span className="hidden md:inline" aria-hidden="true" style={{ color: 'var(--border-color)' }}>|</span>
        <span className="hidden md:flex items-center gap-1 font-mono tabular-nums whitespace-nowrap" title="距下次自动刷新">
          <Icon size={10}><circle cx="12" cy="12" r="10" /><polyline points="12 6 12 12 16 14" /></Icon>
          {countdownText}
        </span>
      </div>

      {/* ── 次行: 标题（左） + 层导航（右） ── */}
      <div className="flex items-center justify-between flex-wrap gap-x-3 gap-y-1 py-3 sm:py-4">
        <button
          onClick={() => navigate('/')}
          className="block text-left focus-ring shrink-0"
          style={{ background: 'none', border: 'none', cursor: 'pointer', padding: 0 }}
          title="回到首页"
        >
          <h1 className="masthead-title">SecNews</h1>
        </button>
        <LayerNav pipelineSummary={pipelineSummary} />
      </div>

      {/* ── 第三行: 子导航（层导航下一行，靠右） ── */}
      {subNav.length > 0 && (
        <div className="flex items-center justify-end flex-wrap gap-2 pb-2">
          {subNav.map(item => (
            <button
              key={item.key}
              onClick={() => navigate(item.path)}
              className="ink-chip focus-ring transition-colors"
              style={{
                padding: '3px 9px',
                color: item.active ? 'var(--text-on-light)' : 'var(--text-secondary)',
                backgroundColor: item.active ? 'var(--accent)' : 'var(--bg-hover)',
                borderColor: item.active ? 'var(--accent)' : 'var(--border-color)',
                fontWeight: item.active ? 600 : 400,
              }}
              aria-current={item.active ? 'page' : undefined}
            >
              {item.label}
            </button>
          ))}
        </div>
      )}

      {/* ── 第四行: 标语 ── */}
      <div className="flex items-center justify-between flex-wrap gap-x-3 gap-y-1 pb-2">
        <p className="text-[11.5px] tracking-[0.18em] uppercase" style={{ color: 'var(--text-muted)' }}>
          AI时代IT和安全从业者的热点工作站
        </p>
      </div>

      {/* ── 第五行: 操作按钮（靠右） ── */}
      <div className="flex items-center justify-end flex-wrap gap-x-3 gap-y-1.5 pb-1.5">
        <div className="flex items-center gap-1.5">
          {actionButtons}
        </div>
      </div>

      {/* ── 第六行: 层标题（资料层/判断层/行动层） ── */}
      {layerName && (
        <div className="layer-header-accent flex items-center gap-3 pb-3" style={{ borderBottom: '1px solid var(--border-color)', '--header-accent': layerColor } as React.CSSProperties}>
          <h2 className="font-mono text-lg font-bold leading-tight" style={{ color: 'var(--text-primary)' }}>
            {layerName}
          </h2>
          {layerSubtitle && (
            <span className="text-xs tracking-wide" style={{ color: 'var(--text-muted)' }}>
              {layerSubtitle}
            </span>
          )}
        </div>
      )}
    </header>
  );
}