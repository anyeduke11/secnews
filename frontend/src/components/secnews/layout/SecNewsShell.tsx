/**
 * SecNewsShell — 安全看板壳组件
 *
 * Tab 导航 + 子路由容器 + 底部 StatusBar。
 * v0.6.3: workbench 5 视图并入 — 研判 tab (AnalyzeView) + StatusBar 落位此处。
 */
import { Outlet, useLocation, useNavigate } from 'react-router-dom';
import { StatusBar } from './StatusBar';
import { useI18n } from '../../../contexts/I18nContext';

const TAB_KEYS = [
  { key: 'feed', i18n: 'feed.security_news', path: '/secnews/feed' },
  { key: 'pipeline', i18n: 'pipeline.title', path: '/secnews/pipeline' },
  { key: 'knowledge', i18n: 'kb.title', path: '/secnews/knowledge' },
  { key: 'analyze', i18n: 'analyze.title', path: '/secnews/analyze' },
  { key: 'image', i18n: 'image.studio', path: '/secnews/image' },
  { key: 'analytics', i18n: 'analytics.attack_mapping', path: '/secnews/analytics' },
  { key: 'observability', i18n: 'nav.observability', path: '/secnews/observability' },
  { key: 'settings', i18n: 'nav.settings', path: '/secnews/settings' },
] as const;

export function SecNewsShell() {
  const { t } = useI18n();
  const location = useLocation();
  const navigate = useNavigate();

  const activeTab = TAB_KEYS.find(t => location.pathname.startsWith(t.path))?.key ?? 'feed';

  return (
    <div className="flex flex-col min-h-0">
      {/* SecNews 内部 Tab 导航 */}
      <nav className="flex items-center gap-1 px-4 py-2 border-b" style={{ borderColor: 'var(--border-color)' }}>
        <span className="text-xs font-mono font-medium mr-3" style={{ color: 'var(--text-muted)' }}>
          {t('nav.brand')}
        </span>
        {TAB_KEYS.map(tab => (
          <button
            key={tab.key}
            onClick={() => navigate(tab.path)}
            className="px-3 py-1.5 text-xs font-mono rounded-[var(--radius-sm)] transition-colors"
            style={{
              color: activeTab === tab.key ? 'var(--accent)' : 'var(--text-secondary)',
              backgroundColor: activeTab === tab.key ? 'var(--accent-soft)' : 'transparent',
              fontWeight: activeTab === tab.key ? 600 : 400,
            }}
            aria-current={activeTab === tab.key ? 'page' : undefined}
          >
            {t(tab.i18n)}
          </button>
        ))}
      </nav>

      {/* 子路由渲染区 */}
      <div className="flex-1 overflow-auto p-4">
        <Outlet />
      </div>

      {/* 底部状态栏 (dsh / 管线队列 / token 日用量) */}
      <StatusBar />
    </div>
  );
}
