/**
 * settings/SettingsPage — 设置页面主入口 / 薄壳 (V2 哨兵化)
 *
 * v0.7.x SettingsHub V2:
 *  - 头部双列 st-head (标题 / 副标题 / 状态徽章 / 操作)
 *  - sidebar 改 st-sidenav-item (图标 + 标签 + 描述 + 状态点)
 *  - 默认 cat=dashboard (哨兵式首屏体检: 8 张 st-tile 跳转 + 4 系统子状态)
 *  - 各区段 (16 个 cat) 共享 .settings-shell 作用域, 借 settings-shell.css 的
 *    --sn-* token 与 st-rule / st-card / st-chip 等原子样式
 *
 * 历史: v0.6.x 原 SettingsPage.tsx 1065 行; v0.7.0 拆 12 文件;
 *       v0.7.x SettingsHub 合并 PipelineSettings / SentinelSettingsPage / ImageStudio;
 *       V2 引入 dashboard 首屏 + 全页面哨兵化。
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
import { ModeSwitcher } from './ModeSwitcher';
import { FeedbackSettings } from './FeedbackSettings';
import { ScenarioModelsPanel } from './ScenarioModelsPanel';
import { SettingsDashboard } from './SettingsDashboard';
import { PipelineSettings } from '../secnews/settings/PipelineSettings';
import { SentinelSettingsPage } from '../sentinel/SentinelSettingsPage';
import { useFeatureFlags } from '../../hooks/useFeatureFlags';
import './settings-shell.css';

export function SettingsPage() {
  const navigate = useNavigate();
  // v0.7.x SettingsHub V2: 默认 cat=dashboard (体检面板) — 哨兵式首屏
  // 旧路由 /secnews/settings /secnews/image /sentinel/settings 携带 cat 跳转
  const search = typeof window !== 'undefined' ? new URLSearchParams(window.location.search) : null;
  const catParam = search?.get('cat') as SectionKey | null;
  const [activeSection, setActiveSection] = useState<SectionKey>(
    catParam && SECTIONS.some(s => s.key === catParam) ? catParam : 'dashboard',
  );
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
      case 'dashboard':
        return <SettingsDashboard onJump={setActiveSection} />;
      case 'general':
        return (
          <div className="space-y-2">
            <ModeSwitcher />
            <GeneralSettings onThemeToggle={toggleTheme} theme={theme} />
          </div>
        );
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
        return features.mcp ? <MCPSettingsCard open={open} /> : (
          <div className="st-info">MCP 扩展未启用</div>
        );
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
      case 'pipeline':
        return <PipelineSettings />;
      case 'sentinel':
        return <SentinelSettingsPage />;
      case 'image_models':
        return (
          <div className="space-y-3">
            <div className="st-card">
              <h3>🖼️ 图片工具 · 模型配置</h3>
              <p className="st-section-desc">
                深度 / 轻度 / 图片 三场景的模型选择在这里配置; 文生图与图理解功能已下线 (用户裁决 2026-09-02)
              </p>
            </div>
            <ScenarioModelsPanel scope="settings-image-models" compact />
          </div>
        );
      case 'about':
        return <AboutSettings />;
      case 'feedback':
        return <FeedbackSettings />;
    }
  };

  // 当前激活 section 的元数据 — 用于头部标题/副标题
  const active = SECTIONS.find(s => s.key === activeSection);

  return (
    // v0.7.x SettingsHub V2: 全部 16 cat 共享 .settings-shell 作用域
    // settings-shell.css 提供 --sn-* token 与 st-rule / st-card / st-chip 等原子样式
    <div className="settings-shell w-full flex flex-col" style={{ minHeight: 'calc(100dvh - 1.5rem)' }}>
      {/* V2 头部 — st-head 双列: 标题 + 副标题 / 状态徽章 + 操作 */}
      <header className="st-head">
        <div>
          <h1 className="st-title">
            <span style={{ marginRight: 10, color: 'var(--sn-mint)' }}>⚙</span>
            {active?.label ?? '设置'}
          </h1>
          <p className="st-sub2">{active?.desc ?? '系统设置 · 哨兵化首屏'}</p>
        </div>
        <div className="st-headops">
          <span className="st-chip ok" aria-label="设置已就绪">
            <i aria-hidden />就绪
          </span>
          <button
            type="button"
            className="st-btn ghost"
            onClick={() => navigate('/')}
            aria-label="返回首页"
          >
            <Icon size={11}>
              <line x1="19" y1="12" x2="5" y2="12" />
              <polyline points="12 19 5 12 12 5" />
            </Icon>
            返回首页
          </button>
        </div>
      </header>

      {/* 主区域: sidebar + 可滚动内容 — 填满剩余高度 */}
      <div className="flex flex-1 gap-3 min-h-0">
        {/* V2 sidebar — st-sidenav-item: 图标 + 标签 + 描述 + 状态点 */}
        <nav
          className="settings-shell st-sidenav shrink-0 sm:w-[210px] sm:max-h-full"
          aria-label="设置分类"
        >
          {SECTIONS.filter(s => s.key !== 'integration' || features.mcp).map(s => {
            const isActive = activeSection === s.key;
            return (
              <button
                key={s.key}
                type="button"
                onClick={() => setActiveSection(s.key)}
                className={`st-sidenav-item${isActive ? ' active' : ''}`}
                title={s.desc}
                aria-current={isActive ? 'page' : undefined}
              >
                <span className="st-snav-row">
                  <span className="st-snav-icon" aria-hidden>{s.icon}</span>
                  <span className="st-snav-label">{s.label}</span>
                  <span className="st-snav-state" aria-hidden>
                    {isActive ? '●' : '○'}
                  </span>
                </span>
                {s.desc && <span className="st-snav-desc">{s.desc}</span>}
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