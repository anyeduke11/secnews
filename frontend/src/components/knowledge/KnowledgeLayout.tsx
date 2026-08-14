/**
 * KnowledgeLayout — 知识管理页面统一布局
 *
 * 4 大领域共享的页面骨架:
 *  - 顶部 Header: 返回首页 + 标题 + 副标题 + 全局联邦搜索
 *  - 4 Tab 导航卡片: KnowledgeTabs
 *  - 子页面 Outlet
 *
 * 设计与现有 PageLayout / Header 风格保持一致 (v1.9 Editorial 报纸风)。
 */
import React, { useEffect, useState } from 'react';
import { Outlet, useNavigate } from 'react-router-dom';
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
  const navigate = useNavigate();
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
      {/* 顶部 Header — v1.9 Editorial: 下边墨色粗线分隔报头与内容 */}
      <div
        className="flex flex-col sm:flex-row sm:items-center sm:justify-between mb-4 gap-2 pb-3"
        style={{ borderBottom: '2px solid var(--text-primary)' }}
      >
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
            className="font-mono text-lg font-bold flex items-center gap-2 min-w-0"
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

      {/* 知识展示 — 独立入口卡片 */}
      <div
        className="rounded-[var(--radius-md)] p-3.5 cursor-pointer hover:bg-[var(--bg-hover)] transition-colors mb-4"
        style={{ backgroundColor: 'var(--bg-elevated)', border: '1px solid var(--border-color)' }}
        onClick={() => navigate('/knowledge/imported')}
        role="button"
        tabIndex={0}
        onKeyDown={e => { if (e.key === 'Enter') navigate('/knowledge/imported'); }}
      >
        <div className="flex items-center gap-2 mb-2">
          <span
            className="w-6 h-6 rounded-md flex items-center justify-center text-[10px] font-bold"
            style={{
              backgroundColor: 'color-mix(in srgb, var(--accent) 12%, transparent)',
              color: 'var(--accent)',
            }}
          >
            <Icon size={12}>
              <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14" />
              <polyline points="22 4 12 14.01 9 11.01" />
            </Icon>
          </span>
          <h4 className="text-xs font-bold" style={{ color: 'var(--text-primary)' }}>
            知识展示
          </h4>
          <span className="text-[10px]" style={{ color: 'var(--text-muted)' }}>
            5 源聚合
          </span>
        </div>
        <p className="text-[11px]" style={{ color: 'var(--text-secondary)' }}>
          聚合展示 SecNews 收藏 / Cubox / 书签导入 / 归档 / 实时 5 类数据源，支持去重、排序、筛选与分页。
        </p>
        <div className="mt-2 flex items-center gap-1 text-[10px] font-mono" style={{ color: 'var(--accent)' }}>
          <span>浏览全部 ›</span>
        </div>
      </div>

      {/* 子页面内容 */}
      <div className="knowledge-page-outlet">
        <Outlet />
      </div>
    </div>
  );
}
