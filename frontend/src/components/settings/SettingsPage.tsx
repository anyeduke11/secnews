/**
 * settings/SettingsPage — 设置页面主入口 / 薄壳。
 *
 * 拆自原 SettingsPage.tsx (1065 行 → 12 文件, 每文件 ≤ 400 行)。
 * 本文件仅做组合: 激活 section 状态 + 侧边导航 + 各区段组件。
 * 各区段 (通用/采集/网络/同步/集成/密钥/告警/知识库/导出/维护/关于)
 * 的 state 与 fetch 已下沉到各自组件文件。
 *
 * API 保持向后兼容: export function SettingsPage
 * (App.tsx lazy import: import('./components/settings/SettingsPage').then(m => ({ default: m.SettingsPage })))
 */
import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Icon } from '../Icon';
import { SECTIONS } from './sections';
import type { SectionKey } from './sections';
import { QualitySettings } from './QualitySettings';
import { SourceSettings } from './SourceSettings';
import { ProxySettings } from './ProxySettings';
import { MCPSettingsCard } from './MCPSettingsCard';
import { GeneralSettings } from './GeneralSettings';
import { SyncSettings } from './SyncSettings';
import { SecretsStatusCard } from './SecretsStatusCard';
import { AlertSettings } from './AlertSettings';
import { CollectionScheduleInfo } from './CollectionScheduleInfo';
import { KnowledgeSettings } from './KnowledgeSettings';
import { ExportSettings } from './ExportSettings';
import { DatabaseMaintenance } from './DatabaseMaintenance';
import { AboutSettings } from './AboutSettings';
import { useFeatureFlags } from '../../hooks/useFeatureFlags';

export function SettingsPage() {
  const navigate = useNavigate();
  const [activeSection, setActiveSection] = useState<SectionKey>('general');
  const [open] = useState(true);
  // v0.4.3: mcp 扩展关闭时隐藏集成区段 (后端 /api/mcp/* 已 404)
  const features = useFeatureFlags();

  const { theme, toggleTheme } = (() => {
    try {
      const saved = localStorage.getItem('hotspot-theme');
      return {
        theme: (saved === 'dark' ? 'dark' : 'light') as 'dark' | 'light',
        toggleTheme: () => {
          const next = saved === 'dark' ? 'light' : 'dark';
          localStorage.setItem('hotspot-theme', next);
          document.documentElement.setAttribute('data-theme', next);
          window.dispatchEvent(new Event('theme-changed'));
        },
      };
    } catch {
      return { theme: 'light' as const, toggleTheme: () => {} };
    }
  })();

  const renderContent = () => {
    switch (activeSection) {
      case 'general':
        return <GeneralSettings onThemeToggle={toggleTheme} theme={theme} />;
      case 'collection':
        return (
          <div className="space-y-2">
            <CollectionScheduleInfo />
            <QualitySettings open={open} />
            <SourceSettings open={open} />
          </div>
        );
      case 'network':
        return <ProxySettings open={open} />;
      case 'sync':
        return <SyncSettings />;
      case 'integration':
        // v0.4.3: mcp=false 时 MCP 设置卡片隐藏 (后端路由已 404)
        return features.mcp ? <MCPSettingsCard open={open} /> : <div className="text-xs" style={{ color: 'var(--text-muted)' }}>MCP 扩展未启用</div>;
      case 'secrets':
        return <SecretsStatusCard />;
      case 'alerts':
        return <AlertSettings />;
      case 'knowledge':
        return <KnowledgeSettings />;
      case 'export':
        return <ExportSettings />;
      case 'maintenance':
        return <DatabaseMaintenance />;
      case 'about':
        return <AboutSettings />;
    }
  };

  return (
    <div className="w-full flex flex-col" style={{ minHeight: 'calc(100dvh - 1.5rem)' }}>
      {/* 页面标题 — 报纸报眉风格 */}
      <div className="shrink-0 flex items-center justify-between pb-2 mb-3" style={{ borderBottom: '2px solid var(--text-primary)' }}>
        <h1 className="text-sm font-bold tracking-wide" style={{ color: 'var(--text-primary)' }}>
          <span className="font-mono mr-2">{'\u2699'}</span>
          设置
        </h1>
        <button
          onClick={() => navigate('/')}
          className="btn-ghost gap-1.5 px-2 py-1 text-[10px]"
          aria-label="返回首页"
        >
          <Icon size={11}>
            <line x1="19" y1="12" x2="5" y2="12" />
            <polyline points="12 19 5 12 12 5" />
          </Icon>
          <span className="hidden sm:inline">返回首页</span>
        </button>
      </div>

      {/* 主区域：sidebar + 可滚动内容 — 填满剩余高度 */}
      <div className="flex flex-1 gap-3 min-h-0">
        {/* 侧边导航 — 桌面 sticky 竖排, 移动端横向横滚 */}
        <nav
          className="shrink-0 flex flex-row sm:flex-col gap-px overflow-x-auto sm:overflow-y-auto pb-1 sm:pb-0 sm:sticky sm:top-0 sm:self-start sm:w-[78px] sm:max-h-full"
          style={{ scrollbarWidth: 'none' }}
          aria-label="设置分类"
        >
          {SECTIONS.filter(s => s.key !== 'integration' || features.mcp).map(s => {
            const active = activeSection === s.key;
            return (
              <button
                key={s.key}
                onClick={() => setActiveSection(s.key)}
                className="settings-nav-btn"
                title={s.desc}
                style={{
                  backgroundColor: active ? 'var(--accent)' : 'transparent',
                  color: active ? 'var(--text-on-color)' : 'var(--text-secondary)',
                  fontWeight: active ? 700 : 400,
                }}
                aria-current={active ? 'page' : undefined}
              >
                {s.icon}
                <span className="leading-tight">{s.label}</span>
              </button>
            );
          })}
        </nav>

        {/* 内容区 — 独立滚动 */}
        <div className="flex-1 min-w-0 overflow-y-auto pr-0.5" style={{ scrollbarWidth: 'thin' }}>
          {renderContent()}
        </div>
      </div>
    </div>
  );
}

export default SettingsPage;
