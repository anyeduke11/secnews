/**
 * SecNews 域 API 客户端 (Batch 5 裸 fetch 清扫 — 跨组件共用端点收敛)。
 *
 * 只收录 ≥2 个组件共用的端点; 单组件专用的 URL 在组件内常量化。
 * 复用 lib/api 统一封装, 非 2xx 抛 ApiError (含 status, 供 404 gate 分支)。
 *
 *   - GET /api/secnews/pipeline            → getSecNewsPipeline   (PipelineView · KLQueueCard)
 *   - GET /api/kl/pipeline/stats           → getKlPipelineStats   (TokenLedger · StatusBar)
 *   - GET /api/observability/summary       → getObservabilitySummary (ObservabilityDashboard · StatusBar)
 *   - GET /api/observability/alerts/active → getActiveAlerts      (ActiveAlertsBanner · StatusBar)
 *
 * 返回为宽松 dict, 组件层以各自 interface 断言 (与 sources.ts SourceHealthPayload 同策略)。
 */

import { getJSON } from '../lib/api';

/** GET /api/secnews/pipeline — KL 管线观测 (漏斗/队列/死信/存活/台账) */
export function getSecNewsPipeline<T = Record<string, unknown>>(): Promise<T> {
  return getJSON<T>('/api/secnews/pipeline');
}

/** GET /api/kl/pipeline/stats — 管线统计 (队列 + token ledger) */
export function getKlPipelineStats<T = Record<string, unknown>>(): Promise<T> {
  return getJSON<T>('/api/kl/pipeline/stats');
}

/** GET /api/observability/summary — API 观测 1h 摘要 */
export function getObservabilitySummary<T = Record<string, unknown>>(): Promise<T> {
  return getJSON<T>('/api/observability/summary');
}

/** GET /api/observability/alerts/active — 活跃告警 (acked=0) */
export function getActiveAlerts<T = Record<string, unknown>>(): Promise<T> {
  return getJSON<T>('/api/observability/alerts/active');
}
