import React, { MutableRefObject } from 'react';
import { Icon } from './Icon';

interface TopBarProps {
  pageTitle: string;
  pageSubtitle?: string;
  latestIngestionCount: number;
  lastUpdated: string | null;
  refreshIntervalMinutes: number;
  lastAutoRefreshAtRef?: MutableRefObject<number>;
  onOpenSidebar: () => void;
  onRefresh: () => void;
  refreshing?: boolean;
  theme: 'dark' | 'light';
  onThemeToggle: () => void;
  onOpenSettings?: () => void;
  onOpenFavorites?: () => void;
  favoritesCount?: number;
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

export function TopBar({
  pageTitle,
  pageSubtitle,
  latestIngestionCount,
  lastUpdated,
  refreshIntervalMinutes,
  lastAutoRefreshAtRef,
  onOpenSidebar,
  onRefresh,
  refreshing = false,
  theme,
  onThemeToggle,
  onOpenSettings,
  onOpenFavorites,
  favoritesCount = 0,
}: TopBarProps) {
  const intervalMs = Math.max(refreshIntervalMinutes, 1) * 60 * 1000;
  const now = Date.now();
  const lastTick = lastAutoRefreshAtRef?.current ?? now;
  const remainingMs = lastTick + intervalMs - now;
  const lastUpdatedClock = lastUpdated ? formatClock(new Date(lastUpdated)) : '--:--:--';
  const countdownText = remainingMs > 0
    ? formatCountdown(remainingMs, refreshIntervalMinutes)
    : '00:00';

  return (
    <div className="topbar">
      <button
        type="button"
        className="topbar-mobile-toggle focus-ring"
        onClick={onOpenSidebar}
        aria-label="打开导航"
        title="导航"
      >
        <Icon size={14}>
          <line x1="3" y1="6" x2="21" y2="6" />
          <line x1="3" y1="12" x2="21" y2="12" />
          <line x1="3" y1="18" x2="21" y2="18" />
        </Icon>
      </button>

      <div className="topbar-title">
        <span className="topbar-title-main">{pageTitle}</span>
        {pageSubtitle && <span className="topbar-title-sub">{pageSubtitle}</span>}
      </div>

      <div className="topbar-status" aria-label="系统状态">
        <div
          className="topbar-stat"
          title="最近一轮 run_once 新增"
        >
          <span className="topbar-stat-label">实时</span>
          <span className="topbar-stat-accent">{latestIngestionCount}</span>
          <span className="topbar-stat-label">条</span>
        </div>

        {lastUpdated && (
          <div className="topbar-stat" title="最近一次自动更新时间">
            <span className="topbar-stat-label">更新</span>
            <span className="topbar-stat-value">{lastUpdatedClock}</span>
          </div>
        )}

        <div className="topbar-stat" title="距离下次自动刷新">
          <Icon size={11}>
            <circle cx="12" cy="12" r="9" />
            <polyline points="12 7 12 12 15 14" />
          </Icon>
          <span className="topbar-stat-value">{countdownText}</span>
        </div>
      </div>

      <div className="topbar-actions">
        <button
          type="button"
          onClick={onOpenFavorites}
          className="btn-icon focus-ring relative"
          title={`收藏 (${favoritesCount})`}
          aria-label={`收藏 ${favoritesCount} 项`}
        >
          <Icon>
            <polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2" />
          </Icon>
          {favoritesCount > 0 && (
            <span
              className="absolute -top-0.5 -right-0.5 min-w-[15px] h-[15px] px-1 rounded-full text-[9px] font-bold flex items-center justify-center font-mono"
              style={{ backgroundColor: 'var(--color-finance)', color: 'var(--text-on-light)' }}
            >
              {favoritesCount > 99 ? '99+' : favoritesCount}
            </span>
          )}
        </button>

        <button
          type="button"
          onClick={onOpenSettings}
          className="btn-icon focus-ring"
          title="代理设置"
          aria-label="设置"
        >
          <Icon>
            <circle cx="12" cy="12" r="3" />
            <path d="M12 1v3M12 20v3M4.22 4.22l2.12 2.12M17.66 17.66l2.12 2.12M1 12h3M20 12h3M4.22 19.78l2.12-2.12M17.66 6.34l2.12-2.12" />
          </Icon>
        </button>

        <button
          type="button"
          onClick={onThemeToggle}
          className="btn-icon focus-ring"
          title={theme === 'dark' ? '切换亮色主题' : '切换暗色主题'}
          aria-label={theme === 'dark' ? '切换亮色' : '切换暗色'}
        >
          {theme === 'dark' ? (
            <Icon>
              <circle cx="12" cy="12" r="4" />
              <line x1="12" y1="2" x2="12" y2="4" />
              <line x1="12" y1="20" x2="12" y2="22" />
              <line x1="4.93" y1="4.93" x2="6.34" y2="6.34" />
              <line x1="17.66" y1="17.66" x2="19.07" y2="19.07" />
              <line x1="2" y1="12" x2="4" y2="12" />
              <line x1="20" y1="12" x2="22" y2="12" />
              <line x1="4.93" y1="19.07" x2="6.34" y2="17.66" />
              <line x1="17.66" y1="6.34" x2="19.07" y2="4.93" />
            </Icon>
          ) : (
            <Icon>
              <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z" />
            </Icon>
          )}
        </button>

        <button
          type="button"
          onClick={() => window.open('/api/export', '_blank')}
          className="btn-icon focus-ring"
          title="导出静态 HTML 报告"
          aria-label="导出 HTML"
        >
          <Icon>
            <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
            <polyline points="7 10 12 15 17 10" />
            <line x1="12" y1="15" x2="12" y2="3" />
          </Icon>
        </button>

        <button
          type="button"
          onClick={onRefresh}
          disabled={refreshing}
          className="btn-icon focus-ring"
          title={refreshing ? '正在刷新数据…' : '手动刷新数据'}
          aria-label={refreshing ? '刷新中' : '刷新'}
          style={{
            opacity: refreshing ? 0.6 : 1,
            cursor: refreshing ? 'wait' : 'pointer',
          }}
        >
          {refreshing ? (
            <span style={{ display: 'inline-block', animation: 'spin 0.8s linear infinite' }}>
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
  );
}
