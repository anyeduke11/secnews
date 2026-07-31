import React, { useEffect, useState, MutableRefObject } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { CatchupButton } from './CatchupButton';

interface HeaderProps {
  latestIngestionCount: number;
  latestIngestionAt?: string | null;
  lastUpdated: string | null;
  onRefresh: () => void;
  theme: 'dark' | 'light';
  onThemeToggle: () => void;
  onOpenSettings?: () => void;
  onOpenFavorites?: () => void;
  favoritesCount?: number;
  refreshIntervalMinutes?: number;
  lastAutoRefreshAtRef?: MutableRefObject<number>;
  todosOpenCount?: number;
  refreshing?: boolean;
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

type ViewRoute = '/' | '/todos' | '/history' | '/skills' | '/secrets' | '/sync' | '/weekly-report' | '/knowledge' | '/codegarden';

function isActive(locationPath: string, route: ViewRoute): boolean {
  if (route === '/') return locationPath === '/' || locationPath.startsWith('/category/');
  return locationPath.startsWith(route);
}

// v1.9 Editorial: 工具条文字导航（报纸报眉栏目链接）
const NAV_LINKS: Array<{ route: ViewRoute; label: string }> = [
  { route: '/todos', label: '待办' },
  { route: '/history', label: '历史' },
  { route: '/skills', label: 'Skill' },
  { route: '/secrets', label: '密钥' },
  { route: '/sync', label: '同步' },
  { route: '/weekly-report', label: '周报' },
  { route: '/knowledge', label: '知识库' },
  { route: '/codegarden', label: 'CodeGarden' },
];

export function Header({
  latestIngestionCount, lastUpdated, onRefresh, theme, onThemeToggle,
  onOpenSettings, onOpenFavorites, favoritesCount = 0, refreshIntervalMinutes,
  lastAutoRefreshAtRef, todosOpenCount = 0, refreshing = false,
}: HeaderProps) {
  const location = useLocation();
  const navigate = useNavigate();
  const [now, setNow] = useState<number>(Date.now());
  const [secretTTL, setSecretTTL] = useState<number | null>(null);

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

  const navigateTo = (route: ViewRoute) => {
    if (isActive(location.pathname, route)) { navigate('/'); }
    else { navigate(route); }
  };

  const ttlColor = secretTTL != null && secretTTL < 300
    ? 'var(--color-error)'
    : secretTTL != null && secretTTL < 600
      ? 'var(--color-warning)'
      : 'var(--color-success)';

  // v1.9.1 修订: 恢复描边按钮形态, 配色沿用 editorial token (反色激活)
  const navLinks = (extraClass = '') => (
    NAV_LINKS.map((link) => {
      const active = isActive(location.pathname, link.route);
      return (
        <button
          key={link.route}
          onClick={() => navigateTo(link.route)}
          className={`focus-ring whitespace-nowrap transition-colors ${extraClass}`}
          style={{
            color: active ? 'var(--bg-primary)' : 'var(--text-secondary)',
            background: active ? 'var(--text-primary)' : 'transparent',
            border: '1px solid',
            borderColor: active ? 'var(--text-primary)' : 'var(--border-color)',
            borderRadius: 'var(--radius-sm)',
            fontWeight: active ? 700 : 400,
            padding: '3px 9px', cursor: 'pointer',
            fontSize: 'inherit', letterSpacing: '0.02em', lineHeight: 1.4,
          }}
        >
          {link.label}
          {link.route === '/todos' && todosOpenCount > 0 && (
            <span className="font-mono tabular-nums font-bold ml-0.5" style={{ color: active ? 'inherit' : 'var(--accent)', fontSize: '10px' }}>
              {todosOpenCount > 99 ? '99+' : todosOpenCount}
            </span>
          )}
          {link.route === '/secrets' && secretTTL != null && secretTTL > 0 && (
            <span className="font-mono tabular-nums ml-0.5" style={{ color: ttlColor, fontSize: '9px' }}>
              {Math.floor(secretTTL / 60)}:{(secretTTL % 60).toString().padStart(2, '0')}
            </span>
          )}
        </button>
      );
    })
  );

  const actionButtons = (
    <>
      <button onClick={onOpenFavorites} className="nav-btn relative" title={`收藏${favoritesCount > 0 ? ` (${favoritesCount})` : ''}`} style={{ padding: '5px 7px' }}>
        <Icon size={14}><polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2" /></Icon>
        {favoritesCount > 0 && (
          <span className="absolute -top-0.5 -right-0.5 min-w-[14px] h-[14px] px-[3px] rounded-full text-[9px] font-bold flex items-center justify-center" style={{ backgroundColor: 'var(--accent)', color: 'var(--text-on-light)' }}>
            {favoritesCount > 99 ? '99+' : favoritesCount}
          </span>
        )}
      </button>
      <button onClick={onOpenSettings} className="nav-btn" title="设置" style={{ padding: '5px 7px' }}>
        <Icon size={14}><circle cx="12" cy="12" r="3" /><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z" /></Icon>
      </button>
      <button onClick={onThemeToggle} className="nav-btn" title={theme === 'dark' ? '切换日报版' : '切换夜读版'} style={{ padding: '5px 7px' }}>
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
          padding: '5px 7px',
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
      {/* ── 工具条: 栏目导航 (桌面端) ── */}
      <div
        className="hidden lg:flex items-center justify-end gap-3 py-1.5 text-[11.5px]"
        style={{ borderBottom: '1px solid var(--border-light)', color: 'var(--text-muted)' }}
      >
        <nav className="flex items-center gap-1.5" aria-label="功能导航">
          {navLinks()}
        </nav>
      </div>

      {/* ── Masthead: 报头靠左 + 右侧两行堆叠 (上: 动作组 / 下: 日期摄取状态, 均靠右) ── */}
      <div className="flex items-end flex-wrap gap-x-5 gap-y-2 py-4 sm:py-5">
        <button
          onClick={() => navigate('/')}
          className="block text-left focus-ring shrink-0"
          style={{ background: 'none', border: 'none', cursor: 'pointer', padding: 0 }}
          title="回到首页"
        >
          <h1 className="masthead-title">SecNews</h1>
          <p className="mt-1 text-[11.5px] tracking-[0.18em] uppercase" style={{ color: 'var(--text-muted)' }}>
            热点地图 · 每日情报简报
          </p>
        </button>
        <div className="ml-auto flex flex-col items-end gap-1.5 min-w-0">
          <div className="flex items-center justify-end gap-0.5">
            {actionButtons}
          </div>
          <div
            className="flex items-center justify-end flex-wrap gap-x-2.5 gap-y-1 min-w-0 text-[11.5px]"
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
        </div>
      </div>

      {/* ── 移动端: 横向滚动栏目导航 ── */}
      <div className="flex lg:hidden items-center pb-2">
        <nav
          className="flex items-center gap-2 overflow-x-auto text-xs min-w-0"
          style={{ scrollbarWidth: 'none' }}
          aria-label="功能导航"
        >
          {navLinks()}
        </nav>
      </div>
    </header>
  );
}
