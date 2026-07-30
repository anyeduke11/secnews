/**
 * KnowledgeLayout — 知识管理页面统一布局
 *
 * 4 大领域共享的页面骨架:
 *  - 顶部 Header: 返回首页 + 标题 + 副标题 + 全局联邦搜索
 *  - 4 Tab 导航卡片: KnowledgeTabs
 *  - 子页面 Outlet
 *
 * 设计与现有 PageLayout / Header 风格保持一致 (HUD 科技风)。
 */
import React, { useEffect, useState } from 'react';
import { Outlet } from 'react-router-dom';
import { useGoHome } from '../../hooks/useGoHome';
import { Icon } from '../Icon';
import KnowledgeSearchBar from '../KnowledgeSearchBar';
import { KnowledgeTabs, KnowledgeAreaKey, findAreaByPath } from './KnowledgeTabs';

interface KnowledgeLayoutProps {
  /** 可选: 子页面提供各领域条目数, 显示在 tab 卡片右上角 */
  areaCounts?: Partial<Record<KnowledgeAreaKey, number | null>>;
}

export function KnowledgeLayout({ areaCounts }: KnowledgeLayoutProps) {
  const goHome = useGoHome();
  const [activeTitle, setActiveTitle] = useState<string>('导入');

  useEffect(() => {
    const update = () => {
      const area = findAreaByPath(window.location.pathname);
      setActiveTitle(area.shortTitle);
    };
    update();
    window.addEventListener('popstate', update);
    return () => window.removeEventListener('popstate', update);
  }, []);

  return (
    <div className="knowledge-page" data-active-area={activeTitle}>
      {/* 顶部 Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between mb-4 gap-2">
        <div className="flex items-center gap-3 min-w-0">
          <button
            onClick={goHome}
            className="btn-ghost px-2.5 py-1.5 text-xs"
            title="返回首页"
            aria-label="返回首页"
          >
            <Icon>
              <line x1="19" y1="12" x2="5" y2="12" />
              <polyline points="12 19 5 12 12 5" />
            </Icon>
            返回首页
          </button>
          <h2
            className="text-base font-bold flex items-center gap-2 min-w-0"
            style={{ color: 'var(--text-primary)' }}
          >
            <Icon size={16}>
              <path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20" />
              <path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z" />
            </Icon>
            知识管理
          </h2>
          <span
            className="hidden sm:inline text-xs whitespace-nowrap"
            style={{ color: 'var(--text-muted)' }}
          >
            4 大领域 · 信息导入 → 处理数据 → 知识库编译 → 知识复利
          </span>
        </div>
        <div className="flex items-center gap-2 flex-wrap w-full sm:w-auto">
          <KnowledgeSearchBar />
        </div>
      </div>

      {/* 4 大领域导航 */}
      <KnowledgeTabs counts={areaCounts} />

      {/* 子页面内容 */}
      <div className="knowledge-page-outlet">
        <Outlet />
      </div>
    </div>
  );
}
