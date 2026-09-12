/**
 * Codegarden 域 API 客户端。
 *
 * 与后端 backend/api/codegarden.py 对齐, 路径前缀 /api/codegarden。
 * 复用 lib/api 统一封装 (apiFetch / getJSON / postJSON), 错误透传后端 message。
 * 消费方: useCodegardenProjects / useCodegardenOrchestration /
 *         useCodegardenServices / useCodegardenResources。
 *
 * 类型从 types/codegarden.ts 引 (与后端 Pydantic 模型一致)。
 */

import type {
  CgProject,
  CgProjectCreateRequest,
  CgProjectUpdateRequest,
  CgProjectListResponse,
  GithubImportRequest,
  FromKnowledgeRequest,
  CandidatesResponse,
  LifecycleStage,
  CgDependency,
  DepEntityType,
  DepType,
  CgEvent,
  EventType,
  EventStatus,
  EventSourceType,
  Playbook,
  RunPlaybookResponse,
  CgServiceListResponse,
  CgServiceTopology,
  ServiceScanResponse,
  ServiceRuntime,
  ServiceStatus,
  ServiceType,
  CgResource,
  CgResourceListResponse,
  AllocatePortRequest,
  SaveEnvTemplateRequest,
  ResourceType,
  ResourceStatus,
} from '../types/codegarden';
import { getJSON, postJSON, apiFetch } from '../lib/api';

// ---------------------------------------------------------------------------
// 端点常量 (URL 字面量统一收敛于此, 杜绝散落)
// ---------------------------------------------------------------------------
const CG_BASE = '/api/codegarden';
const PROJECTS_URL = `${CG_BASE}/projects`;
const GITHUB_IMPORT_URL = `${CG_BASE}/github/import`;
const FROM_KNOWLEDGE_URL = `${CG_BASE}/from-knowledge`;
const CANDIDATES_URL = `${CG_BASE}/candidates`;
const DEPENDENCIES_URL = `${CG_BASE}/dependencies`;
const EVENTS_URL = `${CG_BASE}/events`;
const PLAYBOOKS_URL = `${CG_BASE}/playbooks`;
const SERVICES_URL = `${CG_BASE}/services`;
const RESOURCES_URL = `${CG_BASE}/resources`;

/** 请求选项 (目前仅透传 AbortSignal, 与 RequestInit 对齐) */
export interface CodegardenRequestOptions {
  signal?: AbortSignal;
}

function buildQuery(q: Record<string, unknown>): string {
  const params = new URLSearchParams();
  for (const [k, v] of Object.entries(q)) {
    if (v === undefined || v === null) continue;
    params.set(k, String(v));
  }
  const s = params.toString();
  return s ? `?${s}` : '';
}

// ===========================================================================
// Projects (useCodegardenProjects)
// ===========================================================================

export interface ListProjectsQuery {
  limit?: number;
  lifecycle_stage?: LifecycleStage;
  source_type?: string;
  type?: string;
  keyword?: string;
}

export function listProjects(
  q: ListProjectsQuery = {},
  opts?: CodegardenRequestOptions,
): Promise<CgProjectListResponse> {
  return getJSON<CgProjectListResponse>(
    `${PROJECTS_URL}${buildQuery(q as Record<string, unknown>)}`,
    { signal: opts?.signal },
  );
}

export function createProject(body: CgProjectCreateRequest): Promise<CgProject> {
  return postJSON<CgProject>(PROJECTS_URL, body);
}

export function updateProject(id: string, body: CgProjectUpdateRequest): Promise<CgProject> {
  return apiFetch<CgProject>(`${PROJECTS_URL}/${encodeURIComponent(id)}`, {
    method: 'PATCH',
    body: JSON.stringify(body),
  });
}

export function deleteProject(id: string): Promise<void> {
  return apiFetch<void>(`${PROJECTS_URL}/${encodeURIComponent(id)}`, { method: 'DELETE' });
}

export function archiveProject(id: string): Promise<CgProject> {
  return postJSON<CgProject>(`${PROJECTS_URL}/${encodeURIComponent(id)}/archive`, undefined);
}

export function restoreProject(id: string): Promise<CgProject> {
  return postJSON<CgProject>(`${PROJECTS_URL}/${encodeURIComponent(id)}/restore`, undefined);
}

export function transitionProject(id: string, to: LifecycleStage): Promise<CgProject> {
  return postJSON<CgProject>(`${PROJECTS_URL}/${encodeURIComponent(id)}/lifecycle`, { to });
}

export interface SyncTriggerPayload {
  task_id: number;
}

/**
 * 触发 upstream 同步。后端 github_token 未配置 / secrets 未解锁时返回
 * 424 Failed Dependency, detail.message 已带用户可行动指引
 * ("github_token 未配置; 请在 Secrets 页面添加 ..." / "secrets 未解锁; ..."),
 * apiFetch 直接透传该 message。
 */
export function syncProjectUpstream(id: string): Promise<SyncTriggerPayload> {
  return postJSON<SyncTriggerPayload>(
    `${PROJECTS_URL}/${encodeURIComponent(id)}/sync`,
    undefined,
  );
}

/** 同 syncProjectUpstream: 424 时透传后端指引 message */
export function importFromGithub(body: GithubImportRequest): Promise<CgProject> {
  return postJSON<CgProject>(GITHUB_IMPORT_URL, body);
}

/**
 * 从知识库导入项目。201 = 首次转化, 200 = 幂等 (已存在), 两者都返回项目体。
 */
export function importFromKnowledge(body: FromKnowledgeRequest): Promise<CgProject> {
  return postJSON<CgProject>(FROM_KNOWLEDGE_URL, body);
}

/** 面板态: loading / ready / absent (404/405 = 扩展门控关闭, 路由未注册) / failed — SentinelGardenPage 只读观测台专用 */
export type CgPanel<T> =
  | { state: 'loading' }
  | { state: 'ready'; data: T }
  | { state: 'absent'; status: number }
  | { state: 'failed' };

/**
 * 面板级只读 GET, 保留原始 HTTP status 语义 — apiFetch 会把非 ok 归一为 throw,
 * 而观测台需要区分 404 (端点未注册) 与其他失败, 故走显式 Response 处理。
 */
export async function fetchCodegardenPanel<T>(url: string): Promise<CgPanel<T>> {
  try {
    const resp = await fetch(url, { headers: { Accept: 'application/json' } });
    if (resp.status === 404 || resp.status === 405) return { state: 'absent', status: resp.status };
    if (!resp.ok) return { state: 'failed' };
    return { state: 'ready', data: (await resp.json()) as T };
  } catch {
    return { state: 'failed' };
  }
}

/**
 * 同 importFromKnowledge, 但附带 HTTP status — ItemDetailDialog 的提示语需要
 * 区分 201 (首次加入) 与 200 (已存在)。错误路径与原裸 fetch 实现逐字对齐:
 * 非 ok 时抛 `HTTP <status>: <原始响应体文本>`。
 */
export async function importFromKnowledgeWithStatus(
  body: FromKnowledgeRequest,
): Promise<{ status: number; project: CgProject }> {
  const resp = await fetch(FROM_KNOWLEDGE_URL, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!resp.ok) {
    const text = await resp.text().catch(() => '');
    throw new Error(`HTTP ${resp.status}${text ? `: ${text}` : ''}`);
  }
  const project = (await resp.json()) as CgProject;
  return { status: resp.status, project };
}

export function listCandidates(): Promise<CandidatesResponse> {
  return getJSON<CandidatesResponse>(CANDIDATES_URL);
}

// ===========================================================================
// Orchestration: Dependencies / Events / Playbooks (useCodegardenOrchestration)
// ===========================================================================

export interface DependencyListResponse {
  items: CgDependency[];
}

export function listDependencies(limit = 500): Promise<DependencyListResponse> {
  return getJSON<DependencyListResponse>(`${DEPENDENCIES_URL}?limit=${limit}`);
}

export interface AddDependencyRequest {
  source_type: DepEntityType;
  source_id: string;
  target_type: DepEntityType;
  target_id: string;
  dep_type: DepType;
  metadata?: Record<string, unknown>;
}

export function addDependency(body: AddDependencyRequest): Promise<CgDependency> {
  return postJSON<CgDependency>(DEPENDENCIES_URL, body);
}

export function removeDependency(id: string): Promise<void> {
  return apiFetch<void>(`${DEPENDENCIES_URL}/${encodeURIComponent(id)}`, { method: 'DELETE' });
}

export interface DependencyImpactResponse {
  impacts: CgDependency[];
}

export function analyzeDependencyImpact(
  targetType: DepEntityType,
  targetId: string,
  maxDepth = 5,
): Promise<DependencyImpactResponse> {
  return getJSON<DependencyImpactResponse>(
    `${DEPENDENCIES_URL}/impact${buildQuery({
      target_type: targetType,
      target_id: targetId,
      max_depth: maxDepth,
    })}`,
  );
}

export interface ListEventsQuery {
  limit?: number;
  event_type?: EventType;
  status?: EventStatus;
}

export interface EventListResponse {
  items: CgEvent[];
}

export function listEvents(
  q: ListEventsQuery = {},
  opts?: CodegardenRequestOptions,
): Promise<EventListResponse> {
  return getJSON<EventListResponse>(`${EVENTS_URL}${buildQuery(q as Record<string, unknown>)}`, {
    signal: opts?.signal,
  });
}

export interface PublishEventRequest {
  event_type: EventType;
  source_type: EventSourceType;
  source_id: string;
  payload?: Record<string, unknown>;
}

export function publishEvent(body: PublishEventRequest): Promise<CgEvent> {
  return postJSON<CgEvent>(EVENTS_URL, body);
}

export interface PlaybookListResponse {
  items: Playbook[];
}

export function listPlaybooks(): Promise<PlaybookListResponse> {
  return getJSON<PlaybookListResponse>(PLAYBOOKS_URL);
}

export function runPlaybook(name: string, params?: Record<string, unknown>): Promise<RunPlaybookResponse> {
  return postJSON<RunPlaybookResponse>(
    `${PLAYBOOKS_URL}/${encodeURIComponent(name)}/run`,
    { params: params || {} },
  );
}

// ===========================================================================
// Services (useCodegardenServices)
// ===========================================================================

export interface ListServicesQuery {
  limit?: number;
  runtime?: ServiceRuntime;
  status?: ServiceStatus;
  type?: ServiceType;
  keyword?: string;
}

export function listServices(
  q: ListServicesQuery = {},
  opts?: CodegardenRequestOptions,
): Promise<CgServiceListResponse> {
  return getJSON<CgServiceListResponse>(`${SERVICES_URL}${buildQuery(q as Record<string, unknown>)}`, {
    signal: opts?.signal,
  });
}

export function scanServices(): Promise<ServiceScanResponse> {
  return postJSON<ServiceScanResponse>(`${SERVICES_URL}/scan`, undefined);
}

export function restartService(id: string): Promise<SyncTriggerPayload> {
  return postJSON<SyncTriggerPayload>(`${SERVICES_URL}/${encodeURIComponent(id)}/restart`, undefined);
}

export interface ServiceLogsResponse {
  logs?: string;
}

export function getServiceLogs(id: string, tail = 200): Promise<ServiceLogsResponse> {
  return getJSON<ServiceLogsResponse>(`${SERVICES_URL}/${encodeURIComponent(id)}/logs?tail=${tail}`);
}

export function getServiceMetrics(id: string): Promise<Record<string, unknown>> {
  return getJSON<Record<string, unknown>>(`${SERVICES_URL}/${encodeURIComponent(id)}/metrics`);
}

export function getServiceTopology(): Promise<CgServiceTopology> {
  return getJSON<CgServiceTopology>(`${SERVICES_URL}/topology`);
}

// ===========================================================================
// Resources (useCodegardenResources)
// ===========================================================================

export interface ListResourcesQuery {
  limit?: number;
  type?: ResourceType;
  status?: ResourceStatus;
}

export function listResources(
  q: ListResourcesQuery = {},
  opts?: CodegardenRequestOptions,
): Promise<CgResourceListResponse> {
  return getJSON<CgResourceListResponse>(`${RESOURCES_URL}${buildQuery(q as Record<string, unknown>)}`, {
    signal: opts?.signal,
  });
}

export function allocatePort(body: AllocatePortRequest): Promise<CgResource> {
  return postJSON<CgResource>(`${RESOURCES_URL}/allocate-port`, body);
}

export function releasePort(port: number): Promise<void> {
  return postJSON<void>(`${RESOURCES_URL}/release-port?port=${port}`, undefined);
}

export function saveEnvTemplate(body: SaveEnvTemplateRequest): Promise<void> {
  return postJSON<void>(`${RESOURCES_URL}/env-templates`, body);
}

export interface EnvTemplateResponse {
  env_vars?: Record<string, unknown>;
}

export function loadEnvTemplate(name: string): Promise<EnvTemplateResponse> {
  return getJSON<EnvTemplateResponse>(`${RESOURCES_URL}/env-templates?name=${encodeURIComponent(name)}`);
}

export function deleteResource(id: string): Promise<void> {
  return apiFetch<void>(`${RESOURCES_URL}/${encodeURIComponent(id)}`, { method: 'DELETE' });
}
