/**
 * SecNews 域 API 客户端 (Batch 5 裸 fetch 清扫 — 跨组件共用端点收敛)。
 *
 * 只收录 ≥2 个组件共用的端点; 单组件专用的 URL 在组件内常量化。
 * 复用 lib/api 统一封装, 非 2xx 抛 ApiError (含 status, 供 404 gate 分支)。
 *
 *   - GET /api/secnews/pipeline            → getSecNewsPipeline   (PipelineView · KLQueueCard)
 *   - GET /api/observability/summary       → getObservabilitySummary (ObservabilityDashboard · StatusBar)
 *   - GET /api/observability/alerts/active → getActiveAlerts      (ActiveAlertsBanner · StatusBar)
 *
 * 返回为宽松 dict, 组件层以各自 interface 断言 (与 sources.ts SourceHealthPayload 同策略)。
 */

import { apiFetch, getJSON, postJSON } from '../lib/api';

/** GET /api/secnews/pipeline — KL 管线观测 (漏斗/队列/死信/存活/台账) */
export function getSecNewsPipeline<T = Record<string, unknown>>(): Promise<T> {
  return getJSON<T>('/api/secnews/pipeline');
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

// ── Feed (资讯流) ────────────────────────────────────────────────────

export interface FeedItem {
  id: string;
  title: string;
  url: string;
  source: string;
  category: string;
  summary?: string;
  published_at?: string;
}

/** GET /api/secnews/feed — 资讯流分页列表 */
export function getSecNewsFeed(
  params: URLSearchParams,
): Promise<{ items?: FeedItem[]; total?: number }> {
  return getJSON(`/api/secnews/feed?${params.toString()}`);
}

export interface KnowledgeStats {
  items: number;
  concepts: number;
  stage_distribution: Record<string, number>;
}

/** GET /api/secnews/knowledge — 知识条目/概念数 + 阶段分布 */
export function getSecNewsKnowledge(): Promise<KnowledgeStats> {
  return getJSON('/api/secnews/knowledge');
}

/** GET /api/secnews/stats — 资讯全域计数 (sentinel 行动页头部) */
export function getSecNewsStats<T = Record<string, unknown>>(): Promise<T> {
  return getJSON<T>('/api/secnews/stats');
}

// ── 分析 (CVE / LLM 研判 / dsh) ──────────────────────────────────────

export interface RecentCve {
  id: string;
  name: string;
  created_at: string;
}

/** GET /api/cve/recent — 近期 CVE 条目 */
export function getRecentCves(limit = 50): Promise<{ items?: RecentCve[]; total?: number }> {
  return getJSON(`/api/cve/recent?limit=${limit}`);
}

export interface EvalResult {
  score: number;
  reasoning?: string;
  error?: string;
  ok?: boolean;
}

/** POST /api/llm/evaluate — 深度研判评测 (scenario=deep) */
export function evaluateContent(content: string, scenario = 'deep'): Promise<EvalResult> {
  return postJSON('/api/llm/evaluate', { content, scenario });
}

export interface DshTaskResult {
  ok: boolean;
  agent: string;
  result?: number | string;
  error?: string;
  session_id?: string;
}

/** POST /api/dsh/task — 派发 dsh 认知任务 (classify/摘要/实体抽取) */
export function postDshTask(body: {
  task_type: string;
  payload: { content: string };
}): Promise<DshTaskResult> {
  return postJSON('/api/dsh/task', body);
}

export interface ImportResult {
  id: string;
  title: string;
  url: string;
}

/** POST /api/kl/import/url — 抓取 URL 并入库为知识条目 */
export function importKnowledgeUrl(url: string): Promise<ImportResult> {
  return postJSON('/api/kl/import/url', { url });
}

// ── 观测台 (observability) ───────────────────────────────────────────

export interface RecentEvent {
  trace_id: string;
  method: string;
  path_template: string;
  status: number;
  duration_ms: number;
  error: string | null;
  occurred_at: string;
}

/** GET /api/observability/recent — 近期请求事件流 */
export function getObservabilityRecent(limit = 20): Promise<{ items?: RecentEvent[] }> {
  return getJSON(`/api/observability/recent?limit=${limit}`);
}

/** POST /api/observability/alerts/{id}/ack — 确认告警 */
export function ackObservabilityAlert(alertId: number | string): Promise<unknown> {
  return apiFetch(`/api/observability/alerts/${alertId}/ack`, { method: 'POST' });
}

export interface MetricSpec {
  warn?: number;
  critical?: number;
  window_minutes?: number;
}

export interface Thresholds {
  api?: Record<string, MetricSpec>;
  llm?: Record<string, MetricSpec>;
  job?: Record<string, MetricSpec>;
  audit?: Record<string, MetricSpec>;
  alerts?: { channels?: string[]; cooldown_minutes?: number };
}

export interface ThresholdsResp {
  thresholds: Thresholds;
  defaults: Thresholds;
  as_of: string;
}

/** GET /api/observability/thresholds — 告警阈值配置 */
export function getObservabilityThresholds(): Promise<ThresholdsResp> {
  return getJSON('/api/observability/thresholds');
}

/** PUT /api/observability/thresholds — 保存告警阈值配置 */
export function saveObservabilityThresholds(body: { thresholds: Thresholds }): Promise<unknown> {
  return apiFetch('/api/observability/thresholds', {
    method: 'PUT',
    body: JSON.stringify(body),
  });
}

// ── 信息过滤 (info-filter) ───────────────────────────────────────────

export interface FilterRule {
  id: number;
  rule_type: 'allow' | 'deny';
  match_kind: 'category' | 'source_name' | 'source_id' | 'tag';
  match_value: string;
  enabled: number;
  note: string;
  created_at: string;
  updated_at: string;
}

export interface PreviewResult {
  verdict: 'allow' | 'deny' | 'neutral';
  matched_rule: FilterRule | null;
}

export interface GateStatus {
  extension: string;
  is_enabled: boolean;
}

export interface NewFilterRule {
  rule_type: FilterRule['rule_type'];
  match_kind: FilterRule['match_kind'];
  match_value: string;
  note?: string;
}

/** GET /api/info-filter/gate — 过滤器总开关状态 */
export function getInfoFilterGate(): Promise<GateStatus> {
  return getJSON('/api/info-filter/gate');
}

/** GET /api/info-filter/rules — 过滤规则列表 */
export function listInfoFilterRules<T = FilterRule>(): Promise<{ rules?: T[] }> {
  return getJSON<{ rules?: T[] }>('/api/info-filter/rules');
}

/** POST /api/info-filter/rules — 新建过滤规则 */
export function createInfoFilterRule(body: NewFilterRule): Promise<unknown> {
  return postJSON('/api/info-filter/rules', body);
}

/** PATCH /api/info-filter/rules/{id} — 局部更新过滤规则 (启停) */
export function patchInfoFilterRule(id: number, body: { enabled: number }): Promise<unknown> {
  return apiFetch(`/api/info-filter/rules/${id}`, {
    method: 'PATCH',
    body: JSON.stringify(body),
  });
}

/** DELETE /api/info-filter/rules/{id} — 删除过滤规则 */
export function deleteInfoFilterRule(id: number): Promise<unknown> {
  return apiFetch(`/api/info-filter/rules/${id}`, { method: 'DELETE' });
}

/** POST /api/info-filter/preview — 规则预览 (不落库) */
export function previewInfoFilter(body: { category: string; source_name: string }): Promise<PreviewResult> {
  return postJSON('/api/info-filter/preview', body);
}

// ── KL 收件箱 / 存活扫描 / 复利 ─────────────────────────────────────

export interface FileEntry {
  name: string;
  size: number;
  preview?: string;
  quarantined_at?: string;
}

/** GET /api/kl/inbox/list — 收件箱待处理文件 */
export function listKlInbox(): Promise<{ files?: FileEntry[] }> {
  return getJSON('/api/kl/inbox/list');
}

/** POST /api/kl/inbox/scan — 批量扫描收件箱 (移入 wiki / 隔离) */
export function scanKlInbox(): Promise<{
  moved: number;
  quarantined: number;
  quarantine_files?: FileEntry[];
}> {
  return postJSON('/api/kl/inbox/scan', undefined);
}

/** GET /api/kl/quarantine/list — 隔离区文件 */
export function listKlQuarantine(): Promise<{ files?: FileEntry[] }> {
  return getJSON('/api/kl/quarantine/list');
}

/** POST /api/kl/liveness/sweep — 书签存活批扫 */
export function sweepKlLiveness(): Promise<unknown> {
  return postJSON('/api/kl/liveness/sweep', undefined);
}

/** GET /api/kl/compounding — 知识复利面板指标 */
export function getKlCompounding<T = Record<string, unknown>>(): Promise<T> {
  return getJSON<T>('/api/kl/compounding');
}

// ── dsh 认知大脑 (受管子进程) ────────────────────────────────────────

export interface ProcessSnapshot {
  running: boolean;
  pid: number | null;
  uptime_s: number | null;
  restarts: number;
  last_error: string | null;
  log_tail?: string[];
}

export interface DshStatus {
  status: 'connected' | 'starting' | 'stopped' | 'not_configured';
  endpoint: string;
  command_raw: string;
  autostart: boolean;
  configured: boolean;
  endpoint_reachable: boolean;
  process: ProcessSnapshot;
}

export interface DshConfig {
  endpoint: string;
  command: string;
  autostart: boolean;
}

/** GET /api/dsh/control/status — dsh 进程状态 */
export function getDshControlStatus(): Promise<DshStatus> {
  return getJSON('/api/dsh/control/status');
}

/** POST /api/dsh/control/{op} — dsh 启停 (start|stop|restart) */
export function postDshControlOp(op: 'start' | 'stop' | 'restart'): Promise<DshStatus> {
  return apiFetch(`/api/dsh/control/${op}`, { method: 'POST' });
}

/** PUT /api/dsh/control/config — 持久化 dsh 端点/启动命令/自启配置 */
export function updateDshControlConfig(body: DshConfig): Promise<unknown> {
  return apiFetch('/api/dsh/control/config', {
    method: 'PUT',
    body: JSON.stringify(body),
  });
}

// ── 质量看板 ─────────────────────────────────────────────────────────

/** GET /api/quality/summary — 14 道质量门禁汇总 (质量看板 + sentinel 首页) */
export function getQualitySummary<T = Record<string, unknown>>(): Promise<T> {
  return getJSON<T>('/api/quality/summary');
}
