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

import { apiFetch, getJSON } from '../lib/api';

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

// ── 质量门禁拒收回放 (v0.8.6 P1-5, 审计 F1-3) ────────────────────────

export interface QualityRejectionRaw {
  title: string | null;
  url: string | null;
  summary: string | null;
  source_id: string | null;
  published_at: string | null;
}

export interface QualityRejection {
  item_id: string;
  gate_name: string;
  score_deduction: number;
  flags: string[];
  reason: string | null;
  error_msg: string | null;
  checked_at: string;
  mode: string;
  /** raw_items 原文; 缺失 = null (诚实"未留存", 不伪造)。 */
  raw: QualityRejectionRaw | null;
}

/** GET /api/quality/rejections — strict 拒收标记行 + 原文回放 */
export function getQualityRejections(
  hours = 168,
  limit = 50,
): Promise<{ items: QualityRejection[]; total: number; window_hours: number }> {
  return getJSON(`/api/quality/rejections?hours=${hours}&limit=${limit}`);
}

// ── 资讯告警 (2026-09-27 四模式 P1, /api/alerts/v2) ──────────────────

export interface NewsAlertEvent {
  id: number;
  rule_type: string;
  title: string;
  description: string;
  severity: 'critical' | 'high' | 'medium';
  source: string | null;
  source_url: string | null;
  item_id: string | null;
  status: string;
  created_at: string;
}

export const ALERT_RULE_LABELS: Record<string, string> = {
  critical_vuln: '漏洞',
  major_security_event: '安全事件',
  major_ai_security_event: 'AI 安全事件',
  must_know_regulatory: '合规时限',
};

/** GET /api/alerts/v2?rule_type= — 资讯告警 4 规则域列表 (不含 CodeGarden 项目告警) */
export function getNewsAlerts(ruleType?: string): Promise<{ count: number; items: NewsAlertEvent[] }> {
  const qs = ruleType ? `?rule_type=${encodeURIComponent(ruleType)}&limit=100` : '?limit=100';
  return getJSON(`/api/alerts/v2${qs}`);
}

/** GET /api/alerts/v2/unread-count?scope=news — 首页「告警」按钮未读徽标 */
export function getNewsAlertUnread(): Promise<{ count: number }> {
  return getJSON('/api/alerts/v2/unread-count?scope=news');
}

export function markAlertRead(id: number): Promise<unknown> {
  return apiFetch(`/api/alerts/v2/${id}/read`, { method: 'PUT' });
}

export function markAllAlertsRead(): Promise<unknown> {
  return apiFetch('/api/alerts/v2/read-all', { method: 'PUT' });
}

export function resolveAlert(id: number): Promise<unknown> {
  return apiFetch(`/api/alerts/v2/${id}/resolve`, { method: 'PUT' });
}

// ── 精选 (2026-09-27 四模式 P2, /api/hotspots/picked) ────────────────

export interface PickedItem {
  id: string;
  title: string;
  url: string;
  source: string;
  category: string;
  summary: string;
  quality_score: number | null;
  pick_score: number;
  published_at: string | null;
  fetched_at: string;
}

/** GET /api/hotspots/picked — 精选 Top-N (pick_score DESC) */
export function getPickedItems(days = 2, limit = 30): Promise<{ count: number; items: PickedItem[] }> {
  return getJSON(`/api/hotspots/picked?days=${days}&limit=${limit}`);
}
