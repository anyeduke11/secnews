/**
 * WorkbenchLayout — 工作台壳组件 (Phase 4 v0.6)
 *
 * 左侧 5 个视图入口 + 顶部 StatusBar + Outlet。
 * 复用 SecNewsShell 的 Tab 风格 (font-mono + accent-soft 高亮)。
 */
import { Outlet, useLocation, useNavigate } from 'react-router-dom';
import { StatusBar } from './StatusBar';

const TABS = [
  { key: 'briefing', label: '简报', path: '/workbench/briefing' },
  { key: 'pipeline', label: '管线', path: '/workbench/pipeline' },
  { key: 'knowledge', label: '知识', path: '/workbench/knowledge' },
  { key: 'analyze', label: '研判', path: '/workbench/analyze' },
  { key: 'settings', label: '设置', path: '/workbench/settings' },
] as const;

export function WorkbenchLayout() {
  const location = useLocation();
  const navigate = useNavigate();
  const activeTab = TABS.find(t => location.pathname.startsWith(t.path))?.key ?? 'briefing';

  return (
    <div className="flex flex-col min-h-0">
      {/* 顶部导航 + StatusBar */}
      <header className="shrink-0 border-b" style={{ borderColor: 'var(--border-color)' }}>
        <div className="flex items-center px-4 py-2 gap-3">
          <span className="text-xs font-mono font-medium" style={{ color: 'var(--text-muted)' }}>
            工作台
          </span>
          <nav className="flex items-center gap-1 flex-1">
            {TABS.map(tab => (
              <button
                key={tab.key}
                onClick={() => navigate(tab.path)}
                className="px-3 py-1.5 text-xs font-mono rounded-[var(--radius-sm)] transition-colors"
                style={{
                  color: activeTab === tab.key ? 'var(--accent)' : 'var(--text-secondary)',
                  backgroundColor: activeTab === tab.key ? 'var(--accent-soft)' : 'transparent',
                  fontWeight: activeTab === tab.key ? 600 : 400,
                }}
              >
                {tab.label}
              </button>
            ))}
          </nav>
        </div>
        <StatusBar />
      </header>

      {/* 子路由渲染区 */}
      <div className="flex-1 overflow-auto p-4">
        <Outlet />
      </div>
    </div>
  );
}