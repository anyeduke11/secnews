/**
 * feedModel — 资讯域首页 (/ ) 的纯常量 / 纯函数 (B4 从 SentinelHomePage 抽出)
 *
 * 只放无 React 依赖的内容, 便于单测覆盖; 展示区块见 Feed*.tsx。
 */
import { CATEGORIES, type HotspotItem } from '../../../types';

export type ReadMode = 'brief' | 'scan' | 'deep' | 'alert';

export interface QualityGateStat {
  pass: number;
  total: number;
  avg_deduction: number;
}

export interface QualitySummaryRaw {
  summary?: Record<string, QualityGateStat>;
}

/** 频道 chips: 分类 → 哨兵短标签 + 分类色 */
export const CHANNEL_DEFS: { id: string; label: string; color: string }[] = [
  { id: 'all', label: '全部', color: 'var(--sn-mint)' },
  { id: 'ai', label: 'AI', color: 'var(--sn-cat-ai)' },
  { id: 'ai_security', label: 'AI 安全', color: 'var(--sn-cat-ai)' },
  { id: 'security', label: '网络安全', color: 'var(--sn-cat-sec)' },
  { id: 'finance', label: '金融科技', color: 'var(--sn-cat-fin)' },
  { id: 'startup', label: '创投', color: 'var(--sn-cat-vc)' },
  // DEV-0175: bid (招投标) 已随工作台聚焦裁决剔除
  { id: 'github', label: 'GitHub', color: 'var(--sn-cat-git)' },
  { id: 'tech', label: '技术圈', color: 'var(--sn-cat-tech)' },
];

/**
 * 时间窗 chips —— 权威枚举见 backend/domain/enums.py::TimeRange (仅这 4 个值)。
 * `1d` 不在枚举内 (会 400), 因此这里刻意只用 `24h`。
 * `7d` 的语义是「本周周一 00:00 起」而非滚动 7 天, 文案与 title 如实反映。
 */
export const TIME_RANGE_DEFS: { id: string; label: string; hint: string }[] = [
  { id: '24h', label: '24H', hint: '回溯最近 24 小时' },
  { id: '3d', label: '3D', hint: '回溯最近 72 小时' },
  { id: '7d', label: '本周', hint: '本周周一 00:00 起算, 不是滚动 7 天' },
  { id: '30d', label: '30D', hint: '回溯最近 30 天' },
];

/** 关键词防抖 (ms): 避免每次按键都打一次 /api/hotspots */
export const KEYWORD_DEBOUNCE_MS = 300;

/** 后端默认采集间隔 (分钟), 接口不可达时兜底展示 */
export const DEFAULT_COLLECT_MINUTES = 30;

/** SSE collect_done 后资讯域块 (质量门禁 / 精选) 的重拉节流窗口 (ms) */
export const SIDE_RELOAD_GATE_MS = 10_000;

/** 分类 → tag 颜色 (story-top / 次级 / 快讯标签); 复用 CHANNEL_DEFS 的色板, 不重复维护映射 */
export function tagColorOf(category: string): string {
  // 论文: 紫色系复用现有 token (startup 紫), 不新造 CSS 变量
  if (category === 'paper') return 'var(--sn-cat-vc)';
  const hit = CHANNEL_DEFS.find(c => c.id === category);
  return hit && hit.id !== 'all' ? hit.color : 'var(--sn-cat-ai)';
}

/** 复用图标 path (「进入/立即」右箭头): 三处调用共用一份 path 字面量 */
export const ICON_ARROW_D = 'M2.5 7h8M7.5 3.5L11 7l-3.5 3.5';

export function labelOf(category: string): string {
  return CATEGORIES.find(c => c.id === category)?.label ?? category;
}

export function relTime(iso?: string | null): string {
  if (!iso) return '--';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return '--';
  const diff = Date.now() - d.getTime();
  const m = Math.floor(diff / 60000);
  if (m < 1) return '刚刚';
  if (m < 60) return `${m} 分钟前`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h} 小时前`;
  const day = Math.floor(h / 24);
  if (day === 1) return '昨天';
  if (day < 7) return `${day} 天前`;
  return d.toLocaleDateString('zh-CN');
}

export function heatOf(item: HotspotItem): number {
  const s = item.score ?? item.quality_score ?? 0;
  return Math.max(0, Math.min(5, Math.round(s / 20)));
}

export function heatCells(n: number): boolean[] {
  return [1, 2, 3, 4, 5].map(i => i <= n);
}

/** API 来源 href 白名单: 只放行 http(s), javascript:/data: 一律不渲染链接 */
export function safeHref(url: string | null | undefined): string | null {
  if (typeof url !== 'string') return null;
  return /^https?:\/\/\S+$/i.test(url.trim()) ? url.trim() : null;
}