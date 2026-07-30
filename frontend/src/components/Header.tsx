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

  const navigateTo = (route: ViewRoute) => {
    if (isActive(location.pathname, route)) { navigate('/'); }
    else { navigate(route); }
  };

  return (
    <header className="pb-4 mb-4" style={{ borderBottom: '1px solid var(--border-color)' }}>
      {/* Masthead row */}
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-3 shrink-0">
          <div
            className="w-9 h-9 rounded-lg flex items-center justify-center text-sm font-bold shrink-0"
            style={{
              background: 'linear-gradient(135deg, var(--color-ai), color-mix(in srgb, var(--color-ai) 60%, var(--color-startup)))',
              color: '#fff',
              boxShadow: '0 0 12px color-mix(in srgb, var(--color-ai) 35%, transparent)',
            }}
          >
            S
          </div>
          <div className="leading-tight">
            <div className="flex items-center gap-2">
              <h1 className="text-base font-bold tracking-tight" style={{ color: 'var(--text-primary)' }}>
                SecNews
              </h1>
              <span
                className="px-1.5 py-px rounded text-[10px] font-mono tabular-nums font-medium border"
                style={{
                  backgroundColor: 'var(--accent-highlight)',
                  color: 'var(--color-ai)',
                  borderColor: 'color-mix(in srgb, var(--color-ai) 25%, transparent)',
                }}
              >
                v1.6
              </span>
            </div>
            <p className="text-[11px] hidden sm:block" style={{ color: 'var(--text-muted)' }}>
              热点地图 · 每日情报简报
            </p>
          </div>
        </div>

        {/* Center: status bar */}
        <div className="hidden lg:flex items-center gap-2">
          <div
            className="flex items-center gap-2.5 px-3.5 py-1.5 rounded-md"
            style={{
              backgroundColor: 'var(--bg-hover)',
              border: '1px solid var(--border-color)',
            }}
          >
            <span className="flex items-center gap-1.5 text-xs" style={{ color: 'var(--text-secondary)' }}>
              <span className="pulse-dot" style={{ backgroundColor: 'var(--color-general)', width: 5, height: 5, borderRadius: '50%', display: 'inline-block' }} />
              <span className="font-mono tabular-nums font-semibold text-xs" style={{ color: 'var(--color-ai)' }}>{latestIngestionCount}</span>
              <span style={{ color: 'var(--text-muted)' }}>更新</span>
            </span>
            <span className="text-[10px]" style={{ color: 'var(--border-color)' }}>|</span>
            <span className="font-mono tabular-nums text-xs" style={{ color: 'var(--text-secondary)' }} title="最近更新时间">
              {lastUpdatedClock}
            </span>
            <span className="text-[10px]" style={{ color: 'var(--border-color)' }}>|</span>
            <span className="flex items-center gap-1 font-mono tabular-nums text-xs" style={{ color: 'var(--text-muted)' }} title="距下次自动刷新">
              <Icon size={10}><circle cx="12" cy="12" r="10" /><polyline points="12 6 12 12 16 14" /></Icon>
              {countdownText}
            </span>
          </div>
        </div>

        {/* Right: actions */}
        <div className="flex items-center gap-1.5">
          <div className="nav-group hidden sm:flex">
            <button onClick={() => navigateTo('/todos')} className={`nav-btn ${isActive(location.pathname, '/todos') ? 'active' : ''}`} title="待办">
              <Icon size={13}><rect x="8" y="2" width="8" height="4" rx="1" /><path d="M16 4h2a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h2" /><path d="M9 12h6M9 16h4" /></Icon>
              {todosOpenCount > 0 && (
                <span className="font-mono text-[10px] font-bold tabular-nums" style={{ color: 'var(--color-security)' }}>
                  {todosOpenCount > 99 ? '99+' : todosOpenCount}
                </span>
              )}
            </button>
            <button onClick={() => navigateTo('/history')} className={`nav-btn ${isActive(location.pathname, '/history') ? 'active' : ''}`} title="历史">
              <Icon size={13}><path d="M2 3h6a4 4 0 0 1 4 4v14a3 3 0 0 0-3-3H2z" /><path d="M22 3h-6a4 4 0 0 0-4 4v14a3 3 0 0 1 3-3h7z" /></Icon>
            </button>
            <button onClick={() => navigateTo('/skills')} className={`nav-btn ${isActive(location.pathname, '/skills') ? 'active' : ''}`} title="Skill">
              <Icon size={13}><path d="M12 2L2 7l10 5 10-5-10-5z" /><path d="M2 17l10 5 10-5" /><path d="M2 12l10 5 10-5" /></Icon>
            </button>
            <button onClick={() => navigateTo('/secrets')} className={`nav-btn ${isActive(location.pathname, '/secrets') ? 'active' : ''}`} title="密钥">
              <Icon size={13}><rect x="3" y="11" width="18" height="11" rx="2" ry="2" /><path d="M7 11V7a5 5 0 0 1 10 0v4" /></Icon>
              {secretTTL != null && secretTTL > 0 && (
                <span className="font-mono text-[9px] tabular-nums" style={{ color: secretTTL < 300 ? 'var(--color-error)' : secretTTL < 600 ? 'var(--color-warning)' : 'var(--color-success)' }}>
                  {Math.floor(secretTTL / 60)}:{(secretTTL % 60).toString().padStart(2, '0')}
                </span>
              )}
            </button>
            <button onClick={() => navigateTo('/sync')} className={`nav-btn ${isActive(location.pathname, '/sync') ? 'active' : ''}`} title="同步">
              <Icon size={13}><path d="M17.5 19a4.5 4.5 0 1 0 0-9 5.5 5.5 0 0 0-10.95-1A4.5 4.5 0 0 0 6 17.5" /><polyline points="17 8 12 3 7 8" /><line x1="12" y1="3" x2="12" y2="15" /></Icon>
            </button>
            <button onClick={() => navigateTo('/weekly-report')} className={`nav-btn ${isActive(location.pathname, '/weekly-report') ? 'active' : ''}`} title="周报">
              <Icon size={13}><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" /><polyline points="14 2 14 8 20 8" /><line x1="16" y1="13" x2="8" y2="13" /><line x1="16" y1="17" x2="8" y2="17" /></Icon>
            </button>
            <button onClick={() => navigateTo('/knowledge')} className={`nav-btn ${isActive(location.pathname, '/knowledge') ? 'active' : ''}`} title="知识库">
              <Icon size={13}><path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20" /><path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z" /></Icon>
            </button>
            <button onClick={() => navigateTo('/codegarden')} className={`nav-btn ${isActive(location.pathname, '/codegarden') ? 'active' : ''}`} title="CodeGarden">
              <Icon size={13}><path d="M6 3a3 3 0 0 1 3 3v12a3 3 0 0 1-3 3" /><path d="M18 3a3 3 0 0 0-3 3v12a3 3 0 0 0 3 3" /><path d="M9 12h6" /></Icon>
            </button>
          </div>

          <button onClick={onOpenFavorites} className="nav-btn relative" title={`收藏${favoritesCount > 0 ? ` (${favoritesCount})` : ''}`} style={{ padding: '5px 8px' }}>
            <Icon size={14}><polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2" /></Icon>
            {favoritesCount > 0 && (
              <span className="absolute -top-0.5 -right-0.5 min-w-[14px] h-[14px] px-[3px] rounded-full text-[9px] font-bold flex items-center justify-center" style={{ backgroundColor: 'var(--color-finance)', color: 'var(--bg-primary)' }}>
                {favoritesCount > 99 ? '99+' : favoritesCount}
              </span>
            )}
          </button>
          <button onClick={onOpenSettings} className="nav-btn" title="设置" style={{ padding: '5px 8px' }}>
            <Icon size={14}><circle cx="12" cy="12" r="3" /><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z" /></Icon>
          </button>
          <button onClick={onThemeToggle} className="nav-btn" title={theme === 'dark' ? '切换亮色' : '切换暗色'} style={{ padding: '5px 8px' }}>
            {theme === 'dark' ? (
              <Icon size={14}><circle cx="12" cy="12" r="5" /><line x1="12" y1="1" x2="12" y2="3" /><line x1="12" y1="21" x2="12" y2="23" /><line x1="4.22" y1="4.22" x2="5.64" y2="5.64" /><line x1="18.36" y1="18.36" x2="19.78" y2="19.78" /><line x1="1" y1="12" x2="3" y2="12" /><line x1="21" y1="12" x2="23" y2="12" /><line x1="4.22" y1="19.78" x2="5.64" y2="18.36" /><line x1="18.36" y1="5.64" x2="19.78" y2="4.22" /></Icon>
            ) : (
              <Icon size={14}><path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z" /></Icon>
            )}
          </button>
          <CatchupButton />
          <button
            onClick={onRefresh} disabled={refreshing}
            className="flex items-center justify-center w-8 h-8 rounded-md transition-all duration-150 focus-ring"
            style={{
              color: refreshing ? 'var(--text-muted)' : 'var(--color-ai)',
              backgroundColor: refreshing ? 'transparent' : 'var(--accent-highlight)',
              cursor: refreshing ? 'wait' : 'pointer',
              border: refreshing ? '1px solid var(--border-color)' : '1px solid color-mix(in srgb, var(--color-ai) 30%, transparent)',
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
        </div>
      </div>

      {/* Mobile status strip */}
      <div className="flex lg:hidden items-center justify-between mt-3 pt-3" style={{ borderTop: '1px solid var(--border-subtle)' }}>
        <span className="flex items-center gap-1.5 text-[11px]" style={{ color: 'var(--text-muted)' }}>
          <span className="pulse-dot" style={{ backgroundColor: 'var(--color-general)', width: 4, height: 4, borderRadius: '50%' }} />
          <span style={{ color: 'var(--text-secondary)' }}>更新</span>
          <span className="font-mono tabular-nums font-semibold" style={{ color: 'var(--color-ai)' }}>{latestIngestionCount}</span>
        </span>
        <span className="font-mono tabular-nums text-[11px]" style={{ color: 'var(--text-muted)' }}>
          {lastUpdatedClock} · {countdownText}
        </span>
      </div>
    </header>
  );
}