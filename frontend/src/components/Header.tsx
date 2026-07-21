import React, { useEffect, useState, MutableRefObject } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';

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

function pad2(n: number): string {
  return n < 10 ? `0${n}` : `${n}`;
}

function formatClock(d: Date): string {
  return `${pad2(d.getHours())}:${pad2(d.getMinutes())}:${pad2(d.getSeconds())}`;
}

function formatCountdown(ms: number, intervalMinutes: number): string {
  const total = Math.max(0, Math.floor(ms / 1000));
  const h = Math.floor(total / 3600);
  const m = Math.floor((total % 3600) / 60);
  const s = total % 60;
  if (intervalMinutes >= 720) {
    return `${pad2(h)}:${pad2(m)}:${pad2(s)}`;
  }
  return `${pad2(Math.floor(total / 60))}:${pad2(s)}`;
}

import { Icon } from './Icon';

type ViewRoute = '/' | '/todos' | '/history' | '/skills' | '/secrets' | '/sync' | '/weekly-report' | '/knowledge' | '/codegarden';

function isActive(locationPath: string, route: ViewRoute): boolean {
  if (route === '/') return locationPath === '/' || locationPath.startsWith('/category/');
  return locationPath.startsWith(route);
}

export function Header({
  latestIngestionCount,
  latestIngestionAt,
  lastUpdated,
  onRefresh,
  theme,
  onThemeToggle,
  onOpenSettings,
  onOpenFavorites,
  favoritesCount = 0,
  refreshIntervalMinutes,
  lastAutoRefreshAtRef,
  todosOpenCount = 0,
  refreshing = false,
}: HeaderProps) {
  const location = useLocation();
  const navigate = useNavigate();
  const [apiVersion, setApiVersion] = useState<string | null>(null);
  const [now, setNow] = useState<number>(Date.now());
  const [secretTTL, setSecretTTL] = useState<number | null>(null);

  useEffect(() => {
    let cancelled = false;
    fetch('/api/health')
      .then(r => r.json())
      .then(data => {
        if (!cancelled && data?.version) setApiVersion(data.version);
      })
      .catch(() => {});
    return () => { cancelled = true; };
  }, []);

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
          if (data.setup && data.unlocked) {
            setSecretTTL(data.remaining_seconds);
          } else {
            setSecretTTL(null);
          }
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
  const countdownText = remainingMs > 0
    ? formatCountdown(remainingMs, intervalMinutes)
    : '00:00';

  const navigateTo = (route: ViewRoute) => {
    if (isActive(location.pathname, route)) {
      navigate('/');
    } else {
      navigate(route);
    }
  };

  const activeStyle = {
    color: 'var(--color-ai)',
    backgroundColor: 'var(--bg-hover)',
    borderBottom: '2px solid var(--color-ai)',
  };

  return (
    <header className="pb-4 mb-6" style={{ borderBottom: '1px solid var(--border-color)' }}>
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div className="flex items-center gap-3">
          <div
            className="w-9 h-9 rounded-[var(--radius-sm)] flex items-center justify-center text-sm font-bold shrink-0"
            style={{
              backgroundColor: 'var(--bg-elevated)',
              border: '1px solid var(--border-color)',
              color: 'var(--color-ai)',
            }}
          >
            H
          </div>
          <div>
            <h1 className="text-lg font-bold tracking-tight" style={{ color: 'var(--text-primary)' }}>
              SecNews热点地图
              {apiVersion && (
                <sub
                  className="ml-1 font-mono font-normal"
                  style={{
                    color: 'var(--text-muted)',
                    fontSize: '10px',
                    fontWeight: 500,
                    letterSpacing: '0.02em',
                  }}
                  title={`API version ${apiVersion}`}
                >
                  v{apiVersion}
                </sub>
              )}
            </h1>
            <p className="text-[11px] mt-px" style={{ color: 'var(--text-secondary)' }}>
              七大领域热点实时聚合
            </p>
          </div>
        </div>

        <div className="flex items-center gap-2">
          <div className="flex items-center gap-1.5 text-xs" style={{ color: 'var(--text-muted)' }}>
            <div
              className="flex items-center gap-1.5 px-2 py-1 rounded-[var(--radius-sm)]"
              style={{ backgroundColor: 'var(--bg-hover)' }}
              title={
                latestIngestionAt
                  ? `最近一轮 run_once 新增 (${latestIngestionAt.slice(11, 19)} UTC)`
                  : '后端尚未完成第一轮采集'
              }
            >
              <span className="pulse-dot" style={{ backgroundColor: 'var(--color-general)' }} />
              <span>实时</span>
              <span className="font-mono tabular-nums" style={{ color: 'var(--color-ai)' }}>
                {latestIngestionCount}
              </span>
              <span>条</span>
            </div>
            {lastUpdated && (
              <>
                <div className="w-px h-3" style={{ backgroundColor: 'var(--border-color)' }} aria-hidden="true" />
                <div
                  className="flex items-center gap-1.5 px-2 py-1 rounded-[var(--radius-sm)] font-mono tabular-nums"
                  style={{ backgroundColor: 'var(--bg-hover)', color: 'var(--text-secondary)' }}
                  title="最近一次自动更新时间"
                >
                  <span>更新</span>
                  <span>{lastUpdatedClock}</span>
                </div>
              </>
            )}
            <div className="w-px h-3" style={{ backgroundColor: 'var(--border-color)' }} aria-hidden="true" />
            <div
              className="flex items-center gap-1.5 px-2 py-1 rounded-[var(--radius-sm)] font-mono tabular-nums"
              style={{ backgroundColor: 'var(--bg-hover)', color: 'var(--text-secondary)' }}
              title="距离下次自动刷新"
            >
              <Icon size={12}>
                <circle cx="12" cy="12" r="10" />
                <polyline points="12 6 12 12 16 14" />
              </Icon>
              <span>{countdownText}</span>
            </div>
          </div>

          <button
            onClick={() => navigateTo('/todos')}
            className="btn-ghost px-2.5 py-1.5 text-xs relative"
            title={isActive(location.pathname, '/todos') ? '返回首页' : '待办'}
            aria-label="待办"
            aria-pressed={isActive(location.pathname, '/todos')}
            style={isActive(location.pathname, '/todos') ? activeStyle : undefined}
          >
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
              <rect x="8" y="2" width="8" height="4" rx="1" />
              <path d="M16 4h2a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h2" />
              <path d="M9 12h6M9 16h4" />
            </svg>
            {todosOpenCount > 0 && (
              <span
                className="absolute flex items-center justify-center rounded-full text-[10px] font-bold"
                style={{ top: 2, right: 2, minWidth: 16, height: 16, padding: '0 4px', backgroundColor: 'var(--color-error)', color: 'var(--text-on-color)' }}
              >
                {todosOpenCount > 99 ? '99+' : todosOpenCount}
              </span>
            )}
          </button>

          <button
            onClick={() => navigateTo('/history')}
            className="btn-ghost px-2.5 py-1.5 text-xs"
            title={isActive(location.pathname, '/history') ? '返回首页' : '查看历史资讯'}
            aria-label={isActive(location.pathname, '/history') ? '首页' : '历史'}
            aria-pressed={isActive(location.pathname, '/history')}
            style={isActive(location.pathname, '/history') ? activeStyle : undefined}
          >
            <Icon>
              <path d="M2 3h6a4 4 0 0 1 4 4v14a3 3 0 0 0-3-3H2z" />
              <path d="M22 3h-6a4 4 0 0 0-4 4v14a3 3 0 0 1 3-3h7z" />
            </Icon>
          </button>

          <button
            onClick={() => navigateTo('/skills')}
            className="btn-ghost px-2.5 py-1.5 text-xs"
            title={isActive(location.pathname, '/skills') ? '返回首页' : 'Skill 管理'}
            aria-label={isActive(location.pathname, '/skills') ? '首页' : 'Skill 管理'}
            aria-pressed={isActive(location.pathname, '/skills')}
            style={isActive(location.pathname, '/skills') ? activeStyle : undefined}
          >
            <Icon>
              <path d="M12 2L2 7l10 5 10-5-10-5z" />
              <path d="M2 17l10 5 10-5" />
              <path d="M2 12l10 5 10-5" />
            </Icon>
          </button>

          <button
            onClick={() => navigateTo('/secrets')}
            className="btn-ghost px-2.5 py-1.5 text-xs"
            title={isActive(location.pathname, '/secrets') ? '返回首页' : '密钥管理'}
            aria-label={isActive(location.pathname, '/secrets') ? '首页' : '密钥管理'}
            aria-pressed={isActive(location.pathname, '/secrets')}
            style={isActive(location.pathname, '/secrets') ? activeStyle : undefined}
          >
            <Icon>
              <rect x="3" y="11" width="18" height="11" rx="2" ry="2" />
              <path d="M7 11V7a5 5 0 0 1 10 0v4" />
            </Icon>
            {secretTTL != null && secretTTL > 0 && (
              <span
                className="ml-0.5 font-mono text-[10px] tabular-nums"
                style={{
                  color: secretTTL < 300 ? 'var(--color-error)' : secretTTL < 600 ? 'var(--color-warning)' : 'var(--color-success)',
                  animation: secretTTL < 60 ? 'pulse 1s ease-in-out infinite' : undefined,
                }}
              >
                {Math.floor(secretTTL / 60)}:{(secretTTL % 60).toString().padStart(2, '0')}
              </span>
            )}
          </button>

          <button
            onClick={() => navigateTo('/sync')}
            className="btn-ghost px-2.5 py-1.5 text-xs"
            title={isActive(location.pathname, '/sync') ? '返回首页' : '跨端配置同步 (WebDAV)'}
            aria-label={isActive(location.pathname, '/sync') ? '首页' : '跨端配置同步'}
            aria-pressed={isActive(location.pathname, '/sync')}
            style={isActive(location.pathname, '/sync') ? activeStyle : undefined}
          >
            <Icon>
              <path d="M17.5 19a4.5 4.5 0 1 0 0-9 5.5 5.5 0 0 0-10.95-1A4.5 4.5 0 0 0 6 17.5" />
              <polyline points="17 8 12 3 7 8" />
              <line x1="12" y1="3" x2="12" y2="15" />
            </Icon>
          </button>

          <button
            onClick={() => navigateTo('/weekly-report')}
            className="btn-ghost px-2.5 py-1.5 text-xs"
            title={isActive(location.pathname, '/weekly-report') ? '返回首页' : '周报'}
            aria-label={isActive(location.pathname, '/weekly-report') ? '首页' : '周报'}
            aria-pressed={isActive(location.pathname, '/weekly-report')}
            style={isActive(location.pathname, '/weekly-report') ? activeStyle : undefined}
          >
            <Icon>
              <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
              <polyline points="14 2 14 8 20 8" />
              <line x1="16" y1="13" x2="8" y2="13" />
              <line x1="16" y1="17" x2="8" y2="17" />
              <polyline points="10 9 9 9 8 9" />
            </Icon>
          </button>

          <button
            onClick={() => navigateTo('/knowledge')}
            className="btn-ghost px-2.5 py-1.5 text-xs"
            title={isActive(location.pathname, '/knowledge') ? '返回首页' : '知识管理'}
            aria-label={isActive(location.pathname, '/knowledge') ? '首页' : '知识管理'}
            aria-pressed={isActive(location.pathname, '/knowledge')}
            style={isActive(location.pathname, '/knowledge') ? activeStyle : undefined}
          >
            <Icon>
              <path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20" />
              <path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z" />
            </Icon>
          </button>

          <button
            onClick={() => navigateTo('/codegarden')}
            className="btn-ghost px-2.5 py-1.5 text-xs"
            title={isActive(location.pathname, '/codegarden') ? '返回首页' : 'CodeGarden 项目管理'}
            aria-label={isActive(location.pathname, '/codegarden') ? '首页' : 'CodeGarden'}
            aria-pressed={isActive(location.pathname, '/codegarden')}
            style={isActive(location.pathname, '/codegarden') ? activeStyle : undefined}
          >
            <Icon>
              <path d="M12 2C8 2 5 5 5 9c0 3 2 5 4 6 0 2-2 3-2 5h10c0-2-2-3-2-5 2-1 4-3 4-6 0-4-3-7-7-7z" />
              <path d="M9 22h6" />
            </Icon>
          </button>

          <button
            onClick={onOpenFavorites}
            className="btn-ghost px-2.5 py-1.5 text-xs relative"
            title={`收藏${favoritesCount > 0 ? ` (${favoritesCount})` : ''}`}
            aria-label={`收藏 (${favoritesCount})`}
            style={{ color: favoritesCount > 0 ? 'var(--color-warning)' : undefined }}
          >
            <Icon>
              <polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2" />
            </Icon>
            {favoritesCount > 0 && (
              <span
                className="absolute -top-1 -right-1 min-w-[16px] h-[16px] px-1 rounded-full text-[10px] font-bold flex items-center justify-center"
                style={{ backgroundColor: 'var(--color-warning)', color: 'var(--text-on-light)' }}
              >
                {favoritesCount > 99 ? '99+' : favoritesCount}
              </span>
            )}
          </button>

          <button
            onClick={onOpenSettings}
            className="btn-ghost px-2.5 py-1.5 text-xs"
            title="代理设置"
            aria-label="设置"
          >
            <Icon>
              <circle cx="12" cy="12" r="3" />
              <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z" />
            </Icon>
          </button>

          <button
            onClick={onThemeToggle}
            className="btn-ghost px-2.5 py-1.5 text-xs"
            title={theme === 'dark' ? '切换亮色主题' : '切换暗色主题'}
            aria-label={theme === 'dark' ? '切换亮色' : '切换暗色'}
          >
            {theme === 'dark' ? (
              <Icon>
                <circle cx="12" cy="12" r="5" />
                <line x1="12" y1="1" x2="12" y2="3" />
                <line x1="12" y1="21" x2="12" y2="23" />
                <line x1="4.22" y1="4.22" x2="5.64" y2="5.64" />
                <line x1="18.36" y1="18.36" x2="19.78" y2="19.78" />
                <line x1="1" y1="12" x2="3" y2="12" />
                <line x1="21" y1="12" x2="23" y2="12" />
                <line x1="4.22" y1="19.78" x2="5.64" y2="18.36" />
                <line x1="18.36" y1="5.64" x2="19.78" y2="4.22" />
              </Icon>
            ) : (
              <Icon>
                <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z" />
              </Icon>
            )}
          </button>

          <button
            onClick={() => window.open('/api/export', '_blank')}
            className="btn-ghost px-2.5 py-1.5 text-xs"
            title="导出静态 HTML 报告"
            aria-label="导出"
          >
            <Icon>
              <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
              <polyline points="7 10 12 15 17 10" />
              <line x1="12" y1="15" x2="12" y2="3" />
            </Icon>
          </button>

          <button
            onClick={onRefresh}
            disabled={refreshing}
            className="btn-ghost px-2.5 py-1.5 text-xs"
            style={{
              color: refreshing ? 'var(--text-secondary)' : 'var(--text-primary)',
              opacity: refreshing ? 0.75 : 1,
              cursor: refreshing ? 'wait' : undefined,
              transition:
                'color 180ms cubic-bezier(0.16, 1, 0.3, 1), ' +
                'opacity 180ms cubic-bezier(0.16, 1, 0.3, 1), ' +
                'background-color 180ms cubic-bezier(0.16, 1, 0.3, 1)',
            }}
            title={refreshing ? '正在刷新数据…' : '手动刷新数据'}
            aria-label={refreshing ? '刷新中' : '刷新'}
          >
            {refreshing ? (
              <span
                className="inline-block"
                style={{ width: 14, height: 14, animation: 'spin 0.8s linear infinite' }}
                aria-hidden="true"
              >
                <Icon>
                  <path d="M21 12a9 9 0 1 1-6.219-8.56" />
                </Icon>
              </span>
            ) : (
              <Icon>
                <polyline points="23 4 23 10 17 10" />
                <polyline points="1 20 1 14 7 14" />
                <path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15" />
              </Icon>
            )}
          </button>
        </div>
      </div>
    </header>
  );
}
