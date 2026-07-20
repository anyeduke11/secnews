// frontend/src/types/codegarden.ts
// Phase 2a CodeGarden — 与 backend/repository/codegarden_repo.py 输出对齐
// 字段命名 snake_case (与后端 Pydantic v2 model_dump(mode="json") 一致)

export type ProjectType = 'web_application' | 'api_service' | 'cli' | 'crawler' | 'library' | 'experiment';
export type ProjectSourceType = 'vibe' | 'fork' | 'imported' | 'reference';
export type LifecycleStage = 'ideation' | 'prototype' | 'development' | 'testing' | 'running' | 'maintenance' | 'archived' | 'deprecated';
export type SourceTypeDetail = 'trending' | 'github_search' | 'manual';

export interface CgProject {
  id: string;
  name: string;
  display_name: string | null;
  description: string | null;
  type: ProjectType;
  source_type: ProjectSourceType;
  lifecycle_stage: LifecycleStage;
  health_score: number;
  local_path: string | null;
  repo_url: string | null;
  upstream_url: string | null;
  upstream_default_branch: string | null;
  commits_behind: number;
  commits_ahead: number;
  last_synced_at: string | null;
  source_item_id: string | null;       // 反向溯源 knowledge_items.id
  source_type_detail: SourceTypeDetail | null;
  tags: string[];
  tech_stack: string[];
  domain: string | null;
  priority: number;
  active_skill_ids: string[];
  created_at: string;
  last_activity_at: string | null;
  archived_at: string | null;
}

export interface CgProjectStage {
  id: number;
  project_id: string;
  stage_name: string;
  status: 'pending' | 'in_progress' | 'done' | 'skipped';
  started_at: string | null;
  finished_at: string | null;
  notes: string | null;
  stage_order: number;
}

export interface CgProjectLink {
  id: number;
  project_id: string;
  link_type: 'doc' | 'demo' | 'repo' | 'upstream' | 'ci' | 'other';
  url: string;
  title: string | null;
  created_at: string;
}

export interface CgProjectActivity {
  id: number;
  project_id: string;
  activity_type: string;
  content: string | null;
  metadata: Record<string, unknown> | null;
  created_at: string;
}

export interface CgProjectListResponse {
  version: string;
  total: number;
  items: CgProject[];
}

export interface CgProjectCreateRequest {
  name: string;
  display_name?: string;
  description?: string;
  type: ProjectType;
  source_type: ProjectSourceType;
  lifecycle_stage?: LifecycleStage;
  local_path?: string;
  repo_url?: string;
  upstream_url?: string;
  upstream_default_branch?: string;
  source_item_id?: string;
  source_type_detail?: SourceTypeDetail;
  tags?: string[];
  tech_stack?: string[];
  domain?: string;
  priority?: number;
}

export interface CgProjectUpdateRequest {
  display_name?: string;
  description?: string;
  type?: ProjectType;
  lifecycle_stage?: LifecycleStage;
  health_score?: number;
  local_path?: string;
  repo_url?: string;
  upstream_url?: string;
  upstream_default_branch?: string;
  tags?: string[];
  tech_stack?: string[];
  domain?: string;
  priority?: number;
  active_skill_ids?: string[];
}

export interface GithubImportRequest {
  repo_url: string;
  local_path?: string;
  auto_sync?: boolean;              // 默认 true (导入后立即触发首次同步)
  source_type?: ProjectSourceType;  // 覆盖推断 (默认: 有 upstream=fork, 否则 imported)
  source_type_detail?: SourceTypeDetail;
  type?: ProjectType;               // 默认 'library'
  tags?: string[];
  tech_stack?: string[];
  domain?: string;
}

export interface FromKnowledgeRequest {
  item_id: string;
  source_type?: ProjectSourceType;  // 默认 'reference'
  local_path?: string;
  source_type_detail?: SourceTypeDetail;
}

export interface CandidateItem {
  id: string;
  title: string;
  source_url: string;
  domain: string | null;
  topic: string | null;
  ingested_at: string;
  updated_at: string;
}

export interface CandidatesResponse {
  version: string;
  total: number;
  items: CandidateItem[];
}

export interface SyncTriggerResponse {
  task_id: number;
  project_id: string;
}

// GET /api/codegarden/github/metadata?url=... 实际返回结构
// (与 backend/api/codegarden.py github_metadata 端点对齐)
export interface GithubRepoMetadata {
  url: string;
  owner: string;
  repo: string;
  description: string | null;
  default_branch: string;
  language: string | null;
  upstream_url: string | null;
  upstream_default_branch: string | null;
  inferred_source_type: 'fork' | 'imported';
  inferred_type: string;
}

// GET /api/codegarden/projects/{id}/upstream 返回结构
export interface UpstreamStatusResponse {
  project_id: string;
  upstream_url: string;
  upstream_default_branch: string;
  upstream_description: string | null;
  upstream_stars: number;
  upstream_language: string | null;
  commits_behind: number;
  commits_ahead: number;
  last_synced_at: string | null;
  recent_releases: Array<{
    tag: string | null;
    name: string | null;
    published_at: string | null;
    html_url: string | null;
    prerelease: boolean;
  }>;
}

// 色值映射（与后端 PRD 8.2 一致）
export const LIFECYCLE_COLORS: Record<LifecycleStage, string> = {
  ideation: '#7c6aff',
  prototype: '#06b6d4',
  development: '#3b82f6',
  testing: '#f0c929',
  running: '#00c96a',
  maintenance: '#e8891a',
  archived: '#888899',
  deprecated: '#e85d5d',
};

export const LIFECYCLE_LABELS: Record<LifecycleStage, string> = {
  ideation: '构想中',
  prototype: '原型',
  development: '开发中',
  testing: '测试中',
  running: '运行中',
  maintenance: '维护中',
  archived: '已归档',
  deprecated: '已废弃',
};

export const SOURCE_TYPE_LABELS: Record<ProjectSourceType, string> = {
  vibe: '原创',
  fork: 'Fork',
  imported: '导入',
  reference: '参考',
};

// ===========================================================================
// Phase 2b: 服务网格 + 资源中枢 + 联动引擎
// ===========================================================================

// M2 服务网格
export type ServiceType = 'http' | 'websocket' | 'grpc' | 'static' | 'database';
export type ServiceRuntime = 'docker' | 'pm2' | 'system' | 'bare';
export type ServiceStatus = 'running' | 'stopped' | 'error' | 'unknown';

export interface CgService {
  id: string;
  project_id: string | null;
  name: string;
  namespace: string | null;
  type: ServiceType;
  runtime: ServiceRuntime;
  status: ServiceStatus;
  endpoint_host: string | null;
  endpoint_port: number | null;
  endpoint_domain: string | null;
  health_check_type: string | null;
  health_check_path: string | null;
  health_check_interval: number;
  cpu_limit: string | null;
  memory_limit: string | null;
  dependencies: string[];
  env_vars: Record<string, unknown>;
  created_at: string;
  last_checked_at: string | null;
}

export interface CgServiceListResponse {
  items: CgService[];
  total: number;
  limit: number;
  offset: number;
}

export interface CgServiceTopology {
  nodes: Array<{
    id: string;
    type: string;
    position: { x: number; y: number };
    data: {
      label: string;
      service_id: string;
      runtime: ServiceRuntime;
      status: ServiceStatus;
      endpoint_port: number | null;
      runtime_color: string;
      status_color: string;
    };
  }>;
  edges: Array<{
    id: string;
    source: string;
    target: string;
    label: string;
    data: { dep_type: string };
  }>;
}

export interface ServiceScanResponse {
  scanned: number;
  created: number;
  updated: number;
}

// M3 资源中枢
export type ResourceType = 'port' | 'domain' | 'env_template' | 'volume';
export type ResourceStatus = 'allocated' | 'free' | 'reserved';

export interface CgResource {
  id: string;
  type: ResourceType;
  value: string;
  status: ResourceStatus;
  owner_service_id: string | null;
  owner_project_id: string | null;
  metadata: Record<string, unknown>;
  reserved_until: string | null;
  created_at: string;
}

export interface CgResourceListResponse {
  items: CgResource[];
  total: number;
  limit: number;
  offset: number;
}

export interface AllocatePortRequest {
  preferred_port?: number;
  owner_service_id?: string;
  owner_project_id?: string;
  metadata?: Record<string, unknown>;
}

export interface SaveEnvTemplateRequest {
  name: string;
  env_vars: Record<string, unknown>;
  owner_project_id?: string;
}

// M4 联动引擎
export type DepType = 'code' | 'service' | 'data';
export type DepEntityType = 'project' | 'service';

export interface CgDependency {
  id: string;
  source_type: DepEntityType;
  source_id: string;
  target_type: DepEntityType;
  target_id: string;
  dep_type: DepType;
  metadata: Record<string, unknown>;
  created_at: string;
  _depth?: number;  // impact_analysis 返回时附带
}

export type EventType = 'code_push' | 'service_error' | 'port_conflict' | 'dep_update' | 'project_archive';
export type EventSourceType = 'project' | 'service' | 'resource' | 'scheduler';
export type EventStatus = 'pending' | 'processed' | 'failed';

export interface CgEvent {
  id: string;
  event_type: EventType;
  source_type: EventSourceType;
  source_id: string;
  payload: Record<string, unknown>;
  status: EventStatus;
  created_at: string;
  processed_at: string | null;
  error_message: string | null;
}

export interface Playbook {
  name: string;
  path: string;
  content: string;
  size: number;
}

export interface RunPlaybookResponse {
  task_id: number;
  playbook_name: string;
  status: string;
  steps_count: number;
}

// Phase 2b 色值映射
export const SERVICE_RUNTIME_COLORS: Record<ServiceRuntime, string> = {
  docker: '#2496ed',
  pm2: '#61dafb',
  system: '#94a3b8',
  bare: '#6b7280',
};

export const SERVICE_STATUS_COLORS: Record<ServiceStatus, string> = {
  running: '#10b981',
  stopped: '#9ca3af',
  error: '#ef4444',
  unknown: '#fbbf24',
};

export const RESOURCE_TYPE_LABELS: Record<ResourceType, string> = {
  port: '端口',
  domain: '域名',
  env_template: '环境模板',
  volume: '存储卷',
};

export const EVENT_TYPE_LABELS: Record<EventType, string> = {
  code_push: '代码推送',
  service_error: '服务异常',
  port_conflict: '端口冲突',
  dep_update: '依赖更新',
  project_archive: '项目归档',
};

export const EVENT_STATUS_COLORS: Record<EventStatus, string> = {
  pending: '#fbbf24',
  processed: '#10b981',
  failed: '#ef4444',
};

// ===========================================================================
// Phase 2a 补遗 — BatchImportDialog 类型（原本缺失，补回以修复 tsc 错误）
// ===========================================================================
export interface DetectedProject {
  name: string;
  absolute_path: string;
  relative_path: string;
  marker_file: string;
  language: string;
  inferred_type: ProjectType;
  description: string;
  tech_stack: string[];
}

export interface BatchScanResult {
  detected: DetectedProject[];
  message?: string;
  is_temporary?: boolean;
  temp_id?: string;
  source_type?: string;
  scan_root?: string;
}

export interface BatchImportItemRequest {
  name: string;
  absolute_path: string;
  relative_path: string;
  marker_file: string;
  language: string;
  inferred_type: ProjectType;
  description: string;
  tech_stack: string[];
  override_name?: string;
  override_type?: ProjectType;
  override_lifecycle?: LifecycleStage;
  override_description?: string;
  override_tags?: string[];
}

export interface BatchImportRequest {
  projects: BatchImportItemRequest[];
  temp_id?: string;
  source_type: ProjectSourceType;
  default_lifecycle: LifecycleStage;
}

export interface BatchImportResult {
  imported_count: number;
  failed_count: number;
  errors?: Array<{ name: string; error: string }>;
  failed?: Array<{ name: string; error: string }>;
}
