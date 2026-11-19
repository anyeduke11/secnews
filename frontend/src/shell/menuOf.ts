/**
 * shell/menuOf — 四菜单定义 + 版面条 chip 定义 + 路径归属判定
 *
 * 2026-11-17 结构性拆分自 components/sentinel/SentinelShell.tsx, 逻辑逐字搬出 (零行为变更)。
 */
import type { BandItem, SentinelLayer } from './types';

/** NAV4 (2026-09-13): 四菜单壳 — 资讯 / 知识 / 行动 / 设置
 *  - 资讯 → / (情报流 + 质量区 + 深读 + 历史)
 *  - 知识 → /knowledge (知识库 + 图谱 + 能力资产 + 加工工具 + 复习)
 *  - 行动 → /action (今日行动 + 案件队列 + 待办 + 报告 + 泳道)
 *  - 设置 → /settings (全局配置 + 维护诊断 + 扩展域)
 *  守卫 = routes/__tests__/nav4_shell.test.tsx
 *  Phase 2 编辑部形态 (DEV-0181): 导航改排版式 nv (衬线 + accent 下划线), 不再用图标
 */
export const LAYER_DEFS: { layer: SentinelLayer; label: string; sub: string; to: string }[] = [
  { layer: 'data', label: '资讯', sub: '看什么 — 情报流、质量筛选、采集管道', to: '/' },
  { layer: 'knowledge', label: '知识', sub: '沉淀什么 — 知识库、图谱、能力资产', to: '/knowledge' },
  { layer: 'action', label: '行动', sub: '做什么 — 案件、待办、今日行动、产出', to: '/action' },
  { layer: 'settings', label: '设置', sub: '怎么配 — 全局配置、维护诊断、扩展域', to: '/settings' },
];

/** 版面条 (bandnav, 方案A 原型) — 当前菜单的二级域 chip。
 *  gate 项与 routes/index.tsx 的 features.* 条件注册同源: gate 关闭的 chip 不渲染。 */
export const BANDNAV_DEFS: Record<SentinelLayer, BandItem[]> = {
  // 'judge' 是三层时代遗留 union 成员 (menuOf 已不返回, 路由已重定向) — 无二级域
  judge: [],
  data: [
    { label: '情报流', to: '/' },
    { label: '采集管道', to: '/secnews/pipeline', gate: 'secnews' },
    { label: '发行统计', to: '/secnews/analytics', gate: 'secnews' },
    { label: '质量校对', to: '/quality' },
    { label: '历史', to: '/history' },
  ],
  knowledge: [
    { label: '知识库', to: '/knowledge' },
    { label: '前厅', to: '/knowledge/khub' },
    { label: '编目室', to: '/knowledge/library' },
    { label: '图谱', to: '/knowledge/graph' },
    { label: '复习', to: '/knowledge/review' },
    { label: '检索', to: '/search' },
  ],
  action: [
    { label: '今日行动', to: '/action' },
    { label: '通稿审核', to: '/action/events' },
    { label: '报告', to: '/report' },
  ],
  settings: [
    { label: '全局配置', to: '/settings' },
    { label: '维护诊断', to: '/maint' },
  ],
};

/** chip current 判定: '/' 只精确匹配, 其余前缀匹配 (到下一段为止) */
export function chipIsCurrent(pathname: string, to: string): boolean {
  if (to === '/') return pathname === '/';
  return pathname === to || pathname.startsWith(`${to}/`);
}

/** A7 (DEV-0188): 版面条收起态持久化 key — jsdom/隐私模式无 localStorage 时静默降级 */
const BANDNAV_COLLAPSED_KEY = 'bandnav-collapsed';

export function readBandnavCollapsed(): boolean {
  try {
    return window.localStorage.getItem(BANDNAV_COLLAPSED_KEY) === '1';
  } catch {
    return false;
  }
}

export function writeBandnavCollapsed(v: boolean): void {
  try {
    window.localStorage.setItem(BANDNAV_COLLAPSED_KEY, v ? '1' : '0');
  } catch {
    /* 无 storage 环境 — 仅会话内生效 */
  }
}

/**
 * 路径 → 菜单归属 (NAV4: 四菜单壳 active 态判定).
 * 优先级: 精确匹配 > 前缀匹配; 未命中返回 null.
 */
export function menuOf(pathname: string): SentinelLayer | null {
  // 精确匹配 / action / knowledge / settings → 直接归属
  if (pathname === '/' || pathname.startsWith('/judge') || pathname.startsWith('/cases')) return 'data';
  if (pathname.startsWith('/knowledge') || pathname.startsWith('/deep') || pathname.startsWith('/reviews') || pathname.startsWith('/reader')) return 'knowledge';
  if (pathname.startsWith('/action')) return 'action';
  if (pathname.startsWith('/settings') || pathname.startsWith('/maint')) return 'settings';
  // 工具页按语义归属
  if (pathname.startsWith('/report')) return 'action';
  if (pathname.startsWith('/tags') || pathname.startsWith('/extract') || pathname.startsWith('/search')) return 'knowledge';
  if (pathname.startsWith('/quality') || pathname.startsWith('/history')) return 'data';
  if (pathname.startsWith('/secnews')) {
    // secnews 子视图按内容归属: feed/pipeline/analytics→data, knowledge→knowledge, analyze→action, observability→settings
    const sub = pathname.replace(/^\/secnews\/?/, '') || 'feed';
    if (sub === 'feed' || sub === 'pipeline' || sub === 'analytics') return 'data';
    if (sub === 'knowledge') return 'knowledge';
    if (sub === 'analyze') return 'action';
    if (sub === 'observability') return 'settings';
    return 'data'; // 默认归资讯
  }
  return null;
}