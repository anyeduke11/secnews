/**
 * api/settings/intake.ts — 设置域 API 子模块 (前端重构 V1 · B8-c, 2026-11-19)
 *
 * 自原 api/settings.ts (847 行) 按章节边界拆分而来; 函数体 / 接口体 / 端点 URL /
 * method / body 逐字搬移, 零改写。聚合出口仍为 ../api/settings (薄 barrel)。
 *
 * 归属章节: 自动入管
 */
import { apiFetch } from '../../lib/api';

// ---------------------------------------------------------------------------
// 自动入管
// ---------------------------------------------------------------------------

export interface AutoIntakeConfig {
  enabled: boolean;
  min_quality_score: number;
  daily_limit: number;
  require_domain_hit: boolean;
  today_intaken: number;
}

/** GET /api/settings/auto-intake */
export function getAutoIntake(): Promise<AutoIntakeConfig> {
  return apiFetch<AutoIntakeConfig>('/api/settings/auto-intake');
}

/** PATCH /api/settings/auto-intake */
export function patchAutoIntake(next: AutoIntakeConfig): Promise<AutoIntakeConfig> {
  return apiFetch<AutoIntakeConfig>('/api/settings/auto-intake', {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      enabled: next.enabled,
      min_quality_score: next.min_quality_score,
      daily_limit: next.daily_limit,
      require_domain_hit: next.require_domain_hit,
    }),
  });
}
