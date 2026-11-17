/**
 * shell/types — L2 壳层共享类型 (2026-11-17 结构性拆分自 components/sentinel/SentinelShell.tsx)
 *
 * 纯类型文件 (无运行时导出), 逐字搬出原壳内 interface/type 定义。
 */
import type { FeatureFlags } from '../hooks/useFeatureFlags';

export type SentinelLayer = 'data' | 'judge' | 'action' | 'knowledge' | 'settings';

/** 心跳条数据 — shell 拉一次, 供子页复用 (管道口径统一) */
export interface PipeSnapshot {
  active: number;
  stale: number;
  dead: number;
  total: number;
  health: '良好' | '一般' | '告警' | '--';
  sources: SourceHealthRow[];
  /** /api/kl/pipeline/stats — 生命周期漏斗 (旧 workbench StatusBar 常驻项) */
  funnel: { stage: string; count: number }[] | null;
  /** 队列三态; error > 0 时以 amber 提示 */
  queue: { pending: number; running: number; error: number } | null;
}

/** /api/sources/health 单行 — 右栏源监控还需累计产出与最近活动时间 */
export interface SourceHealthRow {
  category: string;
  source_name: string;
  status: string;
  total_items?: number;
  last_seen_at?: string | null;
}

/** 版面条 (bandnav, 方案A 原型) — 当前菜单的二级域 chip。
 *  gate 项与 routes/index.tsx 的 features.* 条件注册同源: gate 关闭的 chip 不渲染。 */
export type BandItem = { label: string; to: string; gate?: keyof FeatureFlags };