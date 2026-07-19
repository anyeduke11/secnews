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
