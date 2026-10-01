/**
 * settings/SettingsPage — 设置页面主入口 / 薄壳 (V2 哨兵化)
 *
 * v0.7.x SettingsHub V2:
 *  - 头部双列 st-head (标题 / 副标题 / 状态徽章 / 操作)
 *  - sidebar 改 st-sidenav-item (图标 + 标签 + 描述 + 状态点)
 *  - 默认 cat=overview (哨兵式首屏体检: 6 张 st-tile 跳转 + 系统子状态)
 *  - 各区段 (7 cat) 共享 .settings-shell 作用域, 借 settings-shell.css 的
 *    --sn-* token 与 st-rule / st-card / st-chip 等原子样式
 *
 * 历史: v0.6.x 原 SettingsPage.tsx 1065 行; v0.7.0 拆 12 文件;
 *       v0.7.x SettingsHub 合并采集/哨兵设置与图片模型三页;
 *       V2 引入 dashboard 首屏 + 全页面哨兵化;
 *       v0.8 P1 新增 info_filter (独立资讯筛选门禁, 归 collection 区).
 */
import { useState } from 'react';
import { useTheme } from '../../contexts/ThemeContext';
import { useGoBack } from '../../hooks/useGoBack';
import { Icon } from '../Icon';
import { SECTIONS, SECTION_GROUP_LABELS } from './sections';
import type { SectionKey } from './sections';
import { ModeSwitcher } from './ModeSwitcher';
import { GeneralSettings } from './GeneralSettings';
import { PracticeDomainsCard } from './PracticeDomainsCard';
import { FeatureGatesCard } from './FeatureGatesCard';
import { ModelsSettings } from './ModelsSettings';
import { CollectionScheduleInfo } from './CollectionScheduleInfo';
import { QualitySettings } from './QualitySettings';
import { SourceSettings } from './SourceSettings';
import { KLQueueCard } from './KLQueueCard';
import { AutoIntakeCard } from './AutoIntakeCard';
import { InfoFilterCard } from '../secnews/settings/InfoFilterCard';
import { ProxySettings } from './ProxySettings';
import { SyncSettings } from './SyncSettings';
import { MCPSettingsCard } from './MCPSettingsCard';
import { SecretsStatusCard } from './SecretsStatusCard';
import { DatabaseMaintenance } from './DatabaseMaintenance';
import { ExportActionsCard } from './ExportActionsCard';
import { DshControlCard } from '../secnews/settings/DshControlCard';
import { RejectionLogCard } from './RejectionLogCard';
import { SettingsDashboard } from './SettingsDashboard';
import { useFeatureFlags } from '../../hooks/useFeatureFlags';
import './settings-shell.css';

export function SettingsPage() {
  // 壳品牌 / 资料层 tab 已能回首页, 页级按钮做智能返回 (有来路回上一页)
  const goBack = useGoBack();
  // v0.7.x SettingsHub V2: 默认 cat=overview (体检面板) — 哨兵式首屏
  // 旧路由 /secnews/settings /secnews/image /sentinel/settings 携带 cat 跳转
  const search = typeof window !== 'undefined' ? new URLSearchParams(window.location.search) : null;
  const catParam = search?.get('cat') as SectionKey | null;
  const [activeSection, setActiveSection] = useState<SectionKey>(
    catParam && SECTIONS.some(s => s.key === catParam) ? catParam : 'overview',
  );
  const [open] = useState(true);
  // v0.4.3: mcp 扩展关闭时隐藏集成区段 (后端 /api/mcp/* 已 404)
  const features = useFeatureFlags();

  // P2 (2026-09-13): ThemeContext 已扩展 3 态 (light/dark/paper), 直接用 setTheme
  const { theme, setTheme: setThemeMode } = useTheme();

  const renderContent = () => {
    switch (activeSection) {
      case 'overview':
        return <SettingsDashboard onJump={setActiveSection} />;
      case 'general':
        return (
          <div className="space-y-2">
            <ModeSwitcher />
            <GeneralSettings theme={theme} onThemeChange={setThemeMode} />
            <PracticeDomainsCard />
            <FeatureGatesCard />
          </div>
        );
      case 'models':
        return <ModelsSettings />;
      case 'collection':
        return (
          <div className="space-y-2">
            <CollectionScheduleInfo />
            <QualitySettings open={open} />
            <SourceSettings open={open} />
            <KLQueueCard />
            <AutoIntakeCard />
            <InfoFilterCard />
          </div>
        );
      case 'network':
        return <ProxySettings open={open} />;
      case 'connectivity':
        return (
          <div className="space-y-2">
            <SyncSettings />
            {features.mcp ? <MCPSettingsCard open={open} /> : (
              <div className="st-info">MCP 扩展未启用（可在「通用 → 能力开关」开启后重启生效）</div>
            )}
            <SecretsStatusCard />
          </div>
        );
      case 'ops':
        return (
          <div className="space-y-2">
            <DatabaseMaintenance />
            <ExportActionsCard />
            <DshControlCard />
            <RejectionLogCard />
          </div>
        );
    }
  };

  // 当前激活 section 的元数据 — 用于头部标题/副标题
  const active = SECTIONS.find(s => s.key === activeSection);

  return (
    // v0.7.x SettingsHub V2: 全部 7 cat 共享 .settings-shell 作用域
    // settings-shell.css 提供 --sn-* token 与 st-rule / st-card / st-chip 等原子样式
    <div className="settings-shell w-full flex flex-col" style={{ minHeight: 'calc(100dvh - 1.5rem)' }}>
      {/* V2 头部 — st-head 双列: 标题 + 副标题 / 状态徽章 + 操作 */}
      <header className="st-head">
        <div>
          <h1 className="st-title">
            <span style={{ marginRight: 10, color: 'var(--sn-mint)' }}>⚙</span>
            {active?.label ?? '设置'}
          </h1>
          <p className="st-sub2">{active?.desc ?? '系统设置 · 配置中心'}</p>
        </div>
        <div className="st-headops">
          <span className="st-chip ok" aria-label="设置已就绪">
            <i aria-hidden />就绪
          </span>
          <button
            type="button"
            className="st-btn ghost"
            onClick={goBack}
            aria-label="返回"
          >
            <Icon size={11}>
              <line x1="19" y1="12" x2="5" y2="12" />
              <polyline points="12 19 5 12 12 5" />
            </Icon>
            返回
          </button>
        </div>
      </header>

      {/* 主区域: sidebar + 可滚动内容 — 填满剩余高度; <640px 上下堆叠 (分类导航横滚一行, 见 settings-shell.css) */}
      <div className="flex flex-col sm:flex-row flex-1 gap-3 min-h-0">
        {/* V2 sidebar — st-sidenav-item: 图标 + 标签 + 描述 + 状态点 */}
        <nav
          className="settings-shell st-sidenav shrink-0 sm:w-[210px] sm:max-h-full"
          aria-label="设置分类"
        >
          {/* c8: 组归组渲染 — 组内序 = SECTIONS 声明序 (7 cat 收窄后无 gate 隐藏项) */}
          {SECTION_GROUP_LABELS.map(({ group, label }) => {
            const items = SECTIONS.filter(s => s.group === group);
            if (items.length === 0) return null;
            return (
              <div className="st-snav-group" key={group}>
                {label && <span className="st-snav-grouplabel" aria-hidden>{label}</span>}
                {items.map(s => {
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
              </div>
            );
          })}
        </nav>

        {/* 内容区 — 独立滚动; B1 (DEV-0192): mixed 版式多卡并排 (宽屏 ≥2 列, 窄屏自动单列) */}
        <div className="flex-1 min-w-0 overflow-y-auto pr-0.5" style={{ scrollbarWidth: 'thin' }}>
          <div className={`set-content${active?.layout === 'mixed' ? ' set-content-mixed' : ''}`}>
            {renderContent()}
          </div>
        </div>
      </div>
    </div>
  );
}

export default SettingsPage;