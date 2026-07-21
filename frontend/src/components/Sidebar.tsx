import React, { useState, useEffect } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { Icon } from './Icon';

export type SidebarRoute =
  | '/'
  | '/todos'
  | '/history'
  | '/knowledge'
  | '/codegarden'
  | '/weekly-report'
  | '/skills'
  | '/secrets'
  | '/sync';

interface NavItem {
  route: SidebarRoute;
  label: string;
  shortLabel?: string;
  icon: React.ReactNode;
  matchPrefix?: string;
}

interface SidebarProps {
  open: boolean;
  onClose: () => void;
  todosOpenCount?: number;
  secretTTL?: number | null;
}

const ITEMS: NavItem[] = [
  {
    route: '/',
    label: '热点地图',
    shortLabel: '热点',
    icon: (
      <Icon size={14}>
        <circle cx="12" cy="12" r="9" />
        <path d="M3 12h18M12 3a14 14 0 0 1 0 18M12 3a14 14 0 0 0 0 18" />
      </Icon>
    ),
    matchPrefix: '/category',
  },
  {
    route: '/todos',
    label: '待办',
    shortLabel: '待办',
    icon: (
      <Icon size={14}>
        <rect x="8" y="2" width="8" height="4" rx="1" />
        <path d="M16 4h2a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h2" />
        <path d="M9 12h6M9 16h4" />
      </Icon>
    ),
  },
  {
    route: '/history',
    label: '历史资讯',
    shortLabel: '历史',
    icon: (
      <Icon size={14}>
        <path d="M2 3h6a4 4 0 0 1 4 4v14a3 3 0 0 0-3-3H2z" />
        <path d="M22 3h-6a4 4 0 0 0-4 4v14a3 3 0 0 1 3-3h7z" />
      </Icon>
    ),
  },
  {
    route: '/knowledge',
    label: '知识管理',
    shortLabel: '知识',
    icon: (
      <Icon size={14}>
        <path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20" />
        <path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z" />
      </Icon>
    ),
  },
  {
    route: '/codegarden',
    label: 'CodeGarden',
    shortLabel: '项目',
    icon: (
      <Icon size={14}>
        <path d="M12 2C8 2 5 5 5 9c0 3 2 5 4 6 0 2-2 3-2 5h10c0-2-2-3-2-5 2-1 4-3 4-6 0-4-3-7-7-7z" />
        <path d="M9 22h6" />
      </Icon>
    ),
  },
  {
    route: '/weekly-report',
    label: '周报',
    shortLabel: '周报',
    icon: (
      <Icon size={14}>
        <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
        <polyline points="14 2 14 8 20 8" />
        <line x1="16" y1="13" x2="8" y2="13" />
        <line x1="16" y1="17" x2="8" y2="17" />
      </Icon>
    ),
  },
  {
    route: '/skills',
    label: 'Skill 管理',
    shortLabel: 'Skill',
    icon: (
      <Icon size={14}>
        <path d="M12 2L2 7l10 5 10-5-10-5z" />
        <path d="M2 17l10 5 10-5" />
        <path d="M2 12l10 5 10-5" />
      </Icon>
    ),
  },
  {
    route: '/secrets',
    label: '密钥管理',
    shortLabel: '密钥',
    icon: (
      <Icon size={14}>
        <rect x="3" y="11" width="18" height="11" rx="2" ry="2" />
        <path d="M7 11V7a5 5 0 0 1 10 0v4" />
      </Icon>
    ),
  },
  {
    route: '/sync',
    label: '跨端同步',
    shortLabel: '同步',
    icon: (
      <Icon size={14}>
        <path d="M17.5 19a4.5 4.5 0 1 0 0-9 5.5 5.5 0 0 0-10.95-1A4.5 4.5 0 0 0 6 17.5" />
        <polyline points="17 8 12 3 7 8" />
        <line x1="12" y1="3" x2="12" y2="15" />
      </Icon>
    ),
  },
];

function isActive(pathname: string, item: NavItem): boolean {
  if (item.matchPrefix) return pathname === item.route || pathname.startsWith(item.matchPrefix);
  return pathname === item.route || pathname.startsWith(item.route + '/');
}

export function Sidebar({ open, onClose, todosOpenCount = 0, secretTTL = null }: SidebarProps) {
  const location = useLocation();
  const navigate = useNavigate();

  const [collapsed, setCollapsed] = useState(false);

  useEffect(() => {
    document.documentElement.style.setProperty(
      '--sidebar-w',
      collapsed ? '56px' : '200px',
    );
  }, [collapsed]);

  const handleClick = (route: SidebarRoute) => {
    onClose();
    if (route === '/') {
      // 已在首页时点击 — 不重复 navigate
      if (location.pathname !== '/') navigate('/');
    } else {
      if (location.pathname !== route) navigate(route);
    }
  };

  return (
    <>
      {/* Mobile backdrop */}
      <div
        className="sidebar-backdrop"
        onClick={onClose}
        style={{
          opacity: open ? 1 : 0,
          pointerEvents: open ? 'auto' : 'none',
        }}
        aria-hidden="true"
      />

      <aside
        className={`sidebar ${open ? 'sidebar-open' : ''} ${collapsed ? 'sidebar-collapsed' : ''}`}
        aria-label="主导航"
      >
        <div className="sidebar-header">
          <div
            className="w-7 h-7 rounded-[var(--radius-sm)] flex items-center justify-center text-[12px] font-bold shrink-0"
            style={{
              backgroundColor: 'var(--bg-elevated)',
              border: '1px solid var(--border-color)',
              color: 'var(--color-ai)',
            }}
            aria-hidden="true"
          >
            S
          </div>
          <div className="sidebar-brand">
            <span className="sidebar-brand-title">SecNews</span>
            <span className="sidebar-brand-sub">v1.4 · AI + 安全工作站</span>
          </div>
          <button
            type="button"
            onClick={() => setCollapsed(c => !c)}
            className="sidebar-toggle"
            aria-label={collapsed ? '展开侧栏' : '收起侧栏'}
            aria-expanded={!collapsed}
            title={collapsed ? '展开侧栏' : '收起侧栏'}
          >
            <Icon size={14}>
              {collapsed ? (
                <polyline points="9 18 15 12 9 6" />
              ) : (
                <polyline points="15 18 9 12 15 6" />
              )}
            </Icon>
          </button>
        </div>

        <nav className="sidebar-nav" aria-label="主导航项">
          {ITEMS.map((item) => {
            const active = isActive(location.pathname, item);
            return (
              <button
                key={item.route}
                type="button"
                onClick={() => handleClick(item.route)}
                className="sidebar-item"
                aria-current={active ? 'page' : undefined}
                title={item.label}
                style={
                  active
                    ? {
                        color: 'var(--color-ai)',
                        backgroundColor: 'var(--bg-hover)',
                        borderLeftColor: 'var(--color-ai)',
                      }
                    : undefined
                }
              >
                <span className="sidebar-item-icon" aria-hidden="true">
                  {item.icon}
                </span>
                {!collapsed && <span className="sidebar-item-label">{item.label}</span>}
                {!collapsed && item.route === '/todos' && todosOpenCount > 0 && (
                  <span
                    className="sidebar-badge"
                    style={{ backgroundColor: 'var(--color-security)', color: 'var(--text-on-color)' }}
                  >
                    {todosOpenCount > 99 ? '99+' : todosOpenCount}
                  </span>
                )}
                {!collapsed && item.route === '/secrets' && secretTTL != null && secretTTL > 0 && (
                  <span
                    className="sidebar-badge"
                    style={{
                      backgroundColor: secretTTL < 300 ? 'color-mix(in srgb, var(--color-error) 15%, transparent)' : 'var(--bg-hover)',
                      color:
                        secretTTL < 300
                          ? 'var(--color-security)'
                          : secretTTL < 600
                          ? 'var(--color-finance)'
                          : 'var(--color-general)',
                      border:
                        secretTTL < 300
                          ? '1px solid color-mix(in srgb, var(--color-error) 30%, transparent)'
                          : '1px solid var(--border-color)',
                    }}
                  >
                    {Math.floor(secretTTL / 60)}:{(secretTTL % 60).toString().padStart(2, '0')}
                  </span>
                )}
              </button>
            );
          })}
        </nav>
      </aside>
    </>
  );
}
