/**
 * LayerHeader — 三层架构统一页面头部
 *
 * Phase 5: 设计治理
 * 提供一致的层标题、副标题、子导航、返回按钮，以及流程路径指示器。
 * 消除各层页面重复的 h2 + p 样式。
 */
import React from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import { Icon } from '../Icon';

/** 子导航链接定义 */
interface LayerSubNav {
  key: string;
  label: string;
  path: string;
  /** 当前是否为活跃子页面 */
  active?: boolean;
}

interface LayerHeaderProps {
  /** 层名称 */
  layerName: string;
  /** 副标题 */
  subtitle: string;
  /** 子导航链接列表 */
  subNav?: LayerSubNav[];
  /** 返回路径（默认返回当前层首页） */
  backPath?: string;
  /** 当前是否在子页面 */
  isSubPage?: boolean;
  /** 右侧额外操作区 */
  actions?: React.ReactNode;
  }

export const FLOW_COLORS: Record<string, string> = {
  data:   'var(--layer-data)',
  judge:  'var(--layer-judge)',
  action: 'var(--layer-action)',
};

/* ─── LayerHeader 组件 ─── */

export function LayerHeader({
  layerName, subtitle, backPath, isSubPage, actions,
}: LayerHeaderProps) {
  const navigate = useNavigate();
  const location = useLocation();

  // 从路径推断当前层色
  const currentLayerKey = location.pathname.startsWith('/judge') ? 'judge'
    : location.pathname.startsWith('/action') ? 'action'
    : 'data';
  const layerColor = FLOW_COLORS[currentLayerKey] || 'var(--accent)';

  return (
    <div className="mb-4">
      {/* 标题行 — 加大字号，强化层次 + 层色左边界线 */}
      <div className="layer-header-accent flex items-center gap-3 pb-3" style={{ borderBottom: '1px solid var(--border-color)', '--header-accent': layerColor } as React.CSSProperties}>
        {isSubPage && (
          <button
            onClick={() => navigate(backPath || '/data')}
            className="btn-ghost px-2.5 py-1.5 text-xs"
            title="返回"
            aria-label="返回"
          >
            <Icon size={14}>
              <line x1="19" y1="12" x2="5" y2="12" />
              <polyline points="12 19 5 12 12 5" />
            </Icon>
            返回
          </button>
        )}
        <h2 className="font-mono text-lg font-bold leading-tight" style={{ color: 'var(--text-primary)' }}>
          {layerName}
        </h2>
        <span className="text-xs tracking-wide" style={{ color: 'var(--text-muted)' }}>
          {subtitle}
        </span>
        {actions && (
          <div className="ml-auto flex items-center gap-2">{actions}</div>
        )}
      </div>
    </div>
  );
}

/**
 * useLayerSubNav — 根据当前路径生成层内子导航
 */
export function useLayerSubNav(
  _basePath: string,
  items: { key: string; label: string; path: string }[],
  currentPath: string,
): LayerSubNav[] {
  return items.map(item => ({
    ...item,
    active: currentPath === item.path || currentPath.startsWith(item.path + '/'),
  }));
}

/**
 * 层内子导航配置
 */
export const DATA_SUB_NAV = [
  { key: 'home',   label: '首页',   path: '/data' },
  { key: 'import', label: '知识导入', path: '/data/import' },
  { key: 'fav',    label: '收藏夹',  path: '/data/favorites' },
  { key: 'history', label: '历史',   path: '/data/history' },
];

export const JUDGE_SUB_NAV = [
  { key: 'home',      label: '首页',    path: '/judge' },
  { key: 'trends',    label: '趋势',    path: '/judge/trends' },
  { key: 'bid',       label: '标讯分析', path: '/judge/bid-analysis' },
  { key: 'quality',   label: '质量门禁', path: '/quality/rejection' },
  { key: 'heatmap',   label: '热力图',  path: '/knowledge/heatmap' },
];

export const ACTION_SUB_NAV = [
  { key: 'home',     label: '首页',     path: '/action' },
  { key: 'report',   label: '报告',     path: '/action/report' },
  { key: 'compound', label: '复利',     path: '/action/compound' },
  { key: 'todos',    label: '待办',     path: '/action/todos' },
  { key: 'bid',      label: '投标',     path: '/action/bid-alert' },
  { key: 'cg',       label: 'CodeGarden', path: '/action/codegarden' },
];