/**
 * Phase 5 前端类型 — 与后端 backend/services/hotspot_service.py 输出完全对齐。
 *
 * 字段命名规则：snake_case（与后端 Pydantic v2 model_dump(mode="json") 一致）。
 * 色值（SPEC §2.2）：与后端权威源严格一致，新增/修改需同步后端。
 */

export interface HotspotItem {
  id: string;
  title: string;
  summary?: string;
  source: string;
  url: string;
  category: 'ai' | 'security' | 'finance' | 'startup' | 'bid' | 'github';
  published_at: string;
  fetched_at?: string;
  // Phase 15: 录入时间(列表排序字段),缺失时回退 fetched_at/published_at
  ingested_at?: string;
  score?: number;
  // Phase 3.5: 质量门禁结果（可空）
  quality_score?: number;
  quality_flags?: string[];
  quality_checked_at?: string;
  is_fallback?: boolean;
  // Phase 20+: 标讯状态(仅 category=bid 有效)
  // 可选值: 招标中 / 中标 / 变更 / 终止 / 成交 / 询价 / 比选 / 其他
  bid_status?: string;
}

export interface CategoryInfo {
  id: string;
  label: string;
  color: string;
  count?: number;
}

export interface TrendPoint {
  label: string;
  hours_ago: number;
  ai: number;
  security: number;
  finance: number;
  startup: number;
  bid: number;
  github: number;
  total: number;
}

export interface HotspotResponse {
  version: string;
  total: number;
  time_range: string;
  category: string;
  keyword: string;
  items: HotspotItem[];
  next_cursor: string | null;
  category_counts: Record<string, number>;
  fetched_at: string;
  // Phase 39: 最近一轮 run_once() 的产出
  // - latest_ingestion_count: 本轮新采集 item 总数
  // - latest_ingestion_at: 本轮 finished_at (ISO), 后端未跑过则为 null
  latest_ingestion_count?: number;
  latest_ingestion_at?: string | null;
}

export interface TrendResponse {
  version: string;
  hours: number;
  trends: TrendPoint[];
  by_category?: boolean;
  data?: Record<string, TrendPoint[]>;
  fetched_at: string;
}

export interface HealthResponse {
  version: string;
  status: 'ok' | 'degraded' | 'down';
  uptime_s: number;
  components: {
    db: { ok: boolean; latency_ms?: number; size_mb: number; wal: { enabled: boolean; mode: string } };
    cache: { ok: boolean; hit_rate: number };
  };
}

export interface QualityRule {
  key: string;
  value: string | number | boolean;
  default: string | number | boolean;
  description?: string;
}

export interface QualityRulesResponse {
  rules: QualityRule[];
  defaults: Record<string, string | number | boolean>;
}

export interface QualitySummary {
  total_checked_24h: number;
  pass_rate_24h: number;
  avg_score_24h: number;
  top_failure_reasons: { reason: string; count: number }[];
}

// Phase 6: /api/stats 响应类型
export interface ConsistencyDrift {
  category: string;
  cached: number;
  db: number;
  note?: string;
}

// Phase 10 收藏类型
export interface FavoriteItem {
  id: number;
  hotspot_id: string;
  category: 'ai' | 'security' | 'finance' | 'startup' | 'bid' | 'github';
  title: string;
  source: string;
  url: string;
  favorited_at: string;
}

export interface FavoritesListResponse {
  version: string;
  category: string;
  total: number;
  count: number;
  items: FavoriteItem[];
}

export interface FavoritesCountResponse {
  version: string;
  total: number;
  by_category: Record<string, number>;
}

export interface AddFavoriteResponse {
  status: string;
  created: boolean;
  item: FavoriteItem;
}

export interface RemoveFavoriteResponse {
  status: string;
  hotspot_id: string;
  removed: number;
}

export interface ConsistencyCheck {
  status: 'ok' | 'drift' | 'unknown';
  drift: ConsistencyDrift[];
  error?: string;
}

// Phase 28 历史资讯类型
export interface Batch {
  batch_no: number;
  start: string;
  end: string;
  item_count: number;
  favorite_count: number;
}

export interface BatchListResponse {
  batches: Batch[];
  total: number;
  next_cursor: number | null;
  has_more: boolean;
}

export interface BatchItemsResponse {
  items: HotspotItem[];
  cursor: string | null;
  has_more: boolean;
}

export interface BatchSummaryResponse {
  batch_no: number;
  start: string;
  end: string;
  total: number;
  source_count: number;
  category_breakdown: Record<string, number>;
  top_sources: { source: string; count: number }[];
}

export interface StatsResponse {
  version: string;
  cache: { stats: Record<string, number>; hit_rate: number };
  db: { hotspots_total: number; size_mb: number; wal: { enabled: boolean; mode: string } };
  uptime_s: number;
  collect_runs_24h: number;
  success_rate_24h: number;
  avg_collect_duration_ms: number;
  last_fallback_at: string | null;
  consistency_check?: ConsistencyCheck;
  time: string;
}

// Phase 5+6: 与后端 SPEC §2.2 严格一致（无 `general` 分类；Phase 6 新增 `github`）
export const CATEGORIES: CategoryInfo[] = [
  { id: 'all', label: '全部热点', color: '#00c96a' },
  { id: 'ai', label: '科技 / AI', color: '#00bcd4' },
  { id: 'security', label: '网络安全', color: '#e85d5d' },
  { id: 'finance', label: '金融 / 投资', color: '#f0c929' },
  { id: 'startup', label: '独立开发 / 创业', color: '#7c6aff' },
  { id: 'bid', label: '招标资讯', color: '#e8891a' },
  { id: 'github', label: 'GitHub 项目', color: '#8b5cf6' },
];

export const CATEGORY_MAP: Record<string, CategoryInfo> = Object.fromEntries(
  CATEGORIES.map(c => [c.id, c])
);

export const TIME_OPTIONS = [
  { value: '24h', label: '24小时' },
  { value: '3d', label: '3天' },
  { value: '7d', label: '7天' },
];

export function getCategoryColor(category: string): string {
  return CATEGORY_MAP[category]?.color ?? '#888899';
}

export function getCategoryLabel(category: string): string {
  return CATEGORY_MAP[category]?.label ?? category;
}

export function formatRelativeTime(isoString: string): string {
  const date = new Date(isoString);
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const diffMins = Math.floor(diffMs / 60000);
  const diffHours = Math.floor(diffMs / 3600000);
  const diffDays = Math.floor(diffMs / 86400000);

  if (diffMins < 1) return '刚刚';
  if (diffMins < 60) return `${diffMins}分钟前`;
  if (diffHours < 24) return `${diffHours}小时前`;
  if (diffDays < 7) return `${diffDays}天前`;

  const month = date.getMonth() + 1;
  const day = date.getDate();
  const hour = date.getHours().toString().padStart(2, '0');
  const min = date.getMinutes().toString().padStart(2, '0');
  return `${month}/${day} ${hour}:${min}`;
}

/**
 * Phase 3.5 质量分三色映射（绿/黄/红）：
 *  - score >= 80 → green
 *  - 50 <= score < 80 → yellow
 *  - score < 50  → red
 */
export function getQualityColor(score?: number | null): string {
  if (score == null) return '#888899';
  if (score >= 80) return '#00c96a';
  if (score >= 50) return '#f0c929';
  return '#e85d5d';
}

// ----- Todos (Phase 36) -----
export type TodoStatus = 'open' | 'done' | 'archived';
export type TodoSourceType = 'favorite' | 'manual';

export interface TodoItem {
  id: number;
  source_type: TodoSourceType;
  source_id: string | null;
  title: string;
  url: string | null;
  source: string | null;
  category: string | null;
  /** Phase 46: 紧急由 deadline 派生 (effective_urgent), 用户不能手动设置。 */
  urgent: boolean;
  important: boolean;
  /** Phase 46: 截止日期 'YYYY-MM-DD' (Asia/Shanghai 时区, 业务日粒度)。null 表示无 deadline。 */
  deadline: string | null;
  note: string | null;
  status: TodoStatus;
  created_at: string;
  updated_at: string;
  completed_at: string | null;
  archived_at: string | null;
}

export interface TodoListResponse {
  version: string;
  total: number;
  items: TodoItem[];
}

export interface TodoCountByPriority {
  urgent_important: number;
  urgent_only: number;
  important_only: number;
  neither: number;
}

export interface TodoCountResponse {
  version: string;
  total: number;
  by_status: Record<TodoStatus, number>;
  by_priority: TodoCountByPriority;
}

export interface TodoCreateRequest {
  source_type: TodoSourceType;
  source_id?: string;
  title: string;
  url?: string;
  source?: string;
  category?: string;
  /** Phase 46: 不再接受 ``urgent``, 紧急由 ``deadline`` 派生。 */
  important?: boolean;
  /** Phase 46: 截止日期 'YYYY-MM-DD'。 */
  deadline?: string | null;
  note?: string;
}

export interface TodoUpdateRequest {
  /** Phase 46: 不再接受 ``urgent``。 */
  important?: boolean;
  /** Phase 46: 截止日期 'YYYY-MM-DD'; 空字符串或 null 表示清空 (不传则保持原值)。 */
  deadline?: string | null;
  status?: TodoStatus;
  note?: string;
}

export interface AvailableFavorite {
  hotspot_id: string;
  title: string;
  url: string | null;
  source: string | null;
  category: string | null;
}

// ----- Phase 41: Skill 管理 -----
export type SkillSource = 'npx' | 'uvx' | 'curl' | 'git' | 'manual';

export interface SkillItem {
  id: number;
  name: string;
  url: string;
  install_command: string;
  description: string | null;
  source: SkillSource;
  tags: string[];
  created_at: string;
  updated_at: string;
}

export interface SkillListResponse {
  version: string;
  total: number;
  items: SkillItem[];
}

export interface SkillCountBySourceResponse {
  version: string;
  counts: Record<string, number>;  // 包含 npx/uvx/curl/git/manual/all
}

export interface SkillCreateRequest {
  name: string;
  url: string;
  install_command: string;
  description?: string;
  source: SkillSource;
  tags?: string[];
}

export interface SkillUpdateRequest {
  name?: string;
  url?: string;
  install_command?: string;
  description?: string;
  source?: SkillSource;
  tags?: string[];
}

// ----- Phase 41: 密钥管理 (LLM API Keys) -----
export interface SecretItem {
  id: number;
  name: string;
  model: string;
  base_url: string;
  api_key_masked: string;
  api_key?: string | null;          // 仅 reveal 后才有
  encryption_key_id: number;
  unlocked?: boolean;               // 当前会话是否解锁
  created_at: string;
  updated_at: string;
}

export interface SecretListResponse {
  version: string;
  total: number;
  items: SecretItem[];
}

export interface SecretStatusResponse {
  version: string;
  setup: boolean;
  unlocked: boolean;
  expires_at: string | null;
  remaining_seconds: number;
  keychain_persisted?: boolean;
}

export interface SecretUnlockResponse {
  version: string;
  encryption_key_id: number;
  unlocked: true;
  expires_at: string;
  ttl_seconds: number;
}

export interface SecretRevealResponse {
  version: string;
  id: number;
  name: string;
  model: string;
  base_url: string;
  api_key: string;
  unlocked: true;
}

export interface SecretTestResponse {
  version: string;
  ok: boolean;
  latency_ms: number;
  status_code: number | null;
  endpoint: string | null;
  model_count?: number | null;
  warning?: string;
  error?: string;
}

export interface SecretImportResponse {
  version: string;
  inserted: number;
  updated: number;
  failures: { name?: string; error: string }[];
  total_secrets: number;
}

export interface SecretCreateRequest {
  name: string;
  model: string;
  base_url: string;
  api_key: string;
  master_key: string;
}

export interface SecretUpdateRequest {
  name?: string;
  model?: string;
  base_url?: string;
  api_key?: string;
  master_key?: string;
}

// ----- Phase 42: 跨端配置同步 (WebDAV) -----
export interface SyncStatusPayload {
  configured: boolean;
  webdav_url?: string;
  webdav_username?: string;
  remote_path?: string;
  effective_remote_path?: string;  // Phase 49: 后端自动生成的 zip 路径 (ASCII)
  effective_display_name?: string;  // Phase 49: manifest 内的中文展示名
  auto_sync_enabled?: boolean;
  auto_sync_interval_minutes?: number;
  last_sync_at?: string | null;
  last_sync_status?: string | null;
  last_sync_error?: string | null;
  last_sync_direction?: string | null;
  device_id?: string;
  created_at?: string;
  updated_at?: string;
}

export interface SyncHistoryItem {
  id: number;
  config_id: number;
  direction: 'push' | 'pull' | 'bidirectional' | 'export' | 'import';
  status: 'success' | 'error' | 'skipped';
  records_count?: number | null;
  conflict_count?: number;
  error_message?: string | null;
  started_at: string;
  finished_at: string;
}

export interface SyncStatusResponse {
  version: string;
  status: SyncStatusPayload;
  recent_history: SyncHistoryItem[];
}

export interface SyncConfigResponse {
  version: string;
  config: {
    id: number;
    name: string;
    webdav_url: string;
    webdav_username: string;
    has_password: boolean;
    remote_path: string;
    auto_sync_enabled: boolean;
    auto_sync_interval_minutes: number;
    last_sync_at: string | null;
    last_sync_status: string | null;
    last_sync_error: string | null;
    last_sync_direction: string | null;
    device_id: string;
    created_at: string;
    updated_at: string;
  };
}

export interface SyncUpsertRequest {
  webdav_url: string;
  webdav_username: string;
  webdav_password?: string;
  master_key: string;
  remote_path?: string;
  auto_sync_enabled?: boolean;
  auto_sync_interval_minutes?: number;
  sync_frequency?: 'manual' | 'daily' | 'weekly' | 'after_collect';
}

export interface SyncTestRequest {
  webdav_url: string;
  webdav_username: string;
  webdav_password: string;
}

export interface SyncTestResponse {
  version: string;
  ok: boolean;
  message: string;
}

export interface SyncPushResponse {
  version: string;
  direction: 'push' | 'pull' | 'bidirectional';
  status: 'success' | 'error' | 'skipped';
  status_code?: number;
  records_count?: number;
  conflict_count?: number;
  table_conflicts?: Record<string, number>;
  remote_path?: string;
  device_id?: string;
  merged_at?: string;
  remote_device_id?: string;
  message?: string;
}

export interface SyncBundlePreview {
  version: string;
  device_id: string;
  merged_at: string;
  record_counts: Record<string, number>;
}

/**
 * Phase 20+ 标讯状态色值映射（与后端 backend/collectors/bid_status.py
 * STATUS_COLOR_MAP 保持一致）：
 *  - 招标中 → 蓝
 *  - 中标/成交 → 绿
 *  - 变更 → 黄
 *  - 终止 → 红
 *  - 询价/比选 → 浅蓝
 *  - 其他 → 灰
 */
// ----- v1.3.0 Phase 4: 周报 -----
export interface WeeklyReport {
  id: number;
  week_start: string;
  week_end: string;
  category_summary: Record<string, number> | string;
  bid_summary: Record<string, number> | string | null;
  trend_weekly: any[] | string;
  top_items: any[] | string;
  source_health: any[] | string;
  favorites_insight: { total: number; by_category: Record<string, number> } | string;
  ai_insight: any | string | null;
  generated_at: string;
  version: string;
}

export function getBidStatusColor(status?: string | null): string {
  if (!status) return '#888899';
  switch (status) {
    case '招标中': return '#3b82f6';   // 蓝
    case '中标':   return '#00c96a';   // 绿
    case '成交':   return '#00c96a';   // 绿
    case '变更':   return '#f0c929';   // 黄
    case '终止':   return '#e85d5d';   // 红
    case '询价':   return '#06b6d4';   // 浅蓝
    case '比选':   return '#06b6d4';   // 浅蓝
    default:       return '#888899';   // 灰
  }
}

// ----- v1.4: 知识管理 (Knowledge Dashboard) -----
export interface KnowledgeItem {
  id: string;
  title: string;
  source: 'cubox' | 'bookmark' | 'secnews' | 'secnews_archive';
  source_url: string;
  domain: string | null;
  topic: string | null;
  type: string | null;
  difficulty: string | null;
  tags: string[];
  concepts: string[];
  mastered: number;
  compiled: boolean;
  ingested_at: string;
  updated_at: string;
}

export interface KnowledgeHealth {
  total_items: number;
  total_concepts: number;
  compiled_ratio: number;
  compiled_count: number;
  orphan_items: number;
  stale_concepts: number;
  gap_analysis?: DomainCoverage[];
}

export interface GraphNode {
  id: string;
  label: string;
  domain: string | null;
  count: number;
  wiki: 'hotspot' | 'local';
}

export interface GraphEdge {
  source: string;
  target: string;
  weight: number;
}

export interface GraphData {
  nodes: GraphNode[];
  edges: GraphEdge[];
}

export interface DomainCoverage {
  domain: string;
  coverage: number;
  suggestion: string;
}

export interface SoulData {
  content: string;
  exists: boolean;
}
