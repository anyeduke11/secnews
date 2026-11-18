/**
 * shell/AppShell — SentinelShell 组件本体 (四菜单唯一壳的组装层)
 *
 * 2026-11-17 结构性拆分自 components/sentinel/SentinelShell.tsx (零行为/零 DOM 变更):
 *  - 壳三段 (Phase 2, DEV-0181, 对齐方案A 原型 masthead/bandnav/pressbar):
 *    MenuNav (报头 + 版面条) → PipeBar (印务条) → children
 *  - 2026-09-10 壳统一: 工具页 (PageLayout) 也走本壳, layer=null 表示无高亮层,
 *    未传 ingested 时壳自取 24h 收录数 (左侧 AppNav 已删除)
 *  - 2026-09-13 NAV4: 三层→四菜单, layer 语义改为 menu key; menuOf() 判定工具页归属
 */
import { useCallback, useEffect, useState } from 'react';
import { useLocation } from 'react-router-dom';
import { useFeatureFlags } from '../hooks/useFeatureFlags';
import { BANDNAV_DEFS, menuOf, readBandnavCollapsed, writeBandnavCollapsed } from './menuOf';
import { fetchIngested24h, PipeProvider } from './pipe';
import { PipeBar } from './PipeBar';
import { MenuNav } from './MenuNav';
import type { SentinelLayer } from './types';
import './shell.css';

export function SentinelShell({ layer, mode = 'brief', ingested, children }: {
  /** 四菜单高亮; null = 工具页 (由 menuOf(pathname) 自动推断归属) */
  layer: SentinelLayer | null;
  mode?: string;
  /** 今日收录: 页面自算则传值 (null = 该页无此口径显示 …); 不传则壳自取 24h total */
  ingested?: number | null;
  children: React.ReactNode;
}) {
  const { pathname } = useLocation();
  const features = useFeatureFlags();

  const [selfIngested, setSelfIngested] = useState<number | null>(null);
  const [bandnavCollapsed, setBandnavCollapsed] = useState(readBandnavCollapsed);
  const shownIngested = ingested === undefined ? selfIngested : ingested;

  const toggleBandnav = useCallback((next: boolean) => {
    setBandnavCollapsed(next);
    writeBandnavCollapsed(next);
  }, []);

  // 菜单 active 态: 优先用显式 layer, 否则按路径推断 (tool 页自动高亮归属菜单)
  const activeLayer = layer ?? menuOf(pathname);
  // 版面条: 当前菜单的二级域 chip (gate 关闭不渲染); 未归属菜单 (如 oauth-callback) 不显示
  const bandItems = activeLayer
    ? BANDNAV_DEFS[activeLayer].filter(it => !it.gate || features[it.gate])
    : [];

  useEffect(() => {
    if (ingested !== undefined) return;
    let alive = true;
    fetchIngested24h().then(n => { if (alive) setSelfIngested(n); });
    return () => { alive = false; };
  }, [ingested]);

  return (
    <PipeProvider>
      <div className={`sentinel${bandnavCollapsed ? ' bandnav-collapsed' : ''}`} data-mode={mode}>
        <MenuNav
          activeLayer={activeLayer}
          bandItems={bandItems}
          collapsed={bandnavCollapsed}
          onToggleBandnav={toggleBandnav}
        />
        <PipeBar ingested={shownIngested} />
        {children}
      </div>
    </PipeProvider>
  );
}