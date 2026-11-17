/**
 * Security 域 API 客户端 (前端重构 V1 · B3 — 安全图谱调用面收敛)。
 *
 * 契约对齐 backend/api/security.py + backend/api/compliance*.py + backend/api/cve*.py。
 * 复用 lib/api 统一封装, 非 2xx 抛 ApiError。
 *
 *   - GET /api/security/graph            → getSecurityGraph     (useSecurityGraph)
 *   - GET /api/compliance/frameworks     → getComplianceFrameworks (useCompliance)
 *   - GET /api/compliance/matrix         → getComplianceMatrix  (useCompliance)
 *   - GET /api/compliance/controls/{evt} → getComplianceControls (useCompliance)
 *   - GET /api/cve/attack-mapping        → getCveAttackMapping  (useAttackMapping)
 *   - GET /api/cve/heatmap               → getCveHeatmap        (useCveHeatmap)
 */

import { getJSON } from '../lib/api';

// ---------------------------------------------------------------------------
// 安全知识图谱 (/api/security/graph)
// ---------------------------------------------------------------------------

/** 图谱节点实体 (后端 security/graph.py to_dict) */
export interface SecurityEntity {
  id: string;
  entity_type: 'tactic' | 'technique' | 'cve' | 'cwe' | 'compliance' | 'product' | 'cpe';
  name: string;
  description?: string;
  external_ref?: string;
  metadata?: Record<string, any>;
}

export interface SecurityGraphResponse {
  ok: boolean;
  nodes: (SecurityEntity & { entity_type: string })[];
  edges: { source_id: string; target_id: string; edge_type: string; weight: number }[];
  stats: {
    tactics: number;
    techniques: number;
    cves: number;
    compliance_items: number;
    knowledge_items: number;
  };
}

/** GET /api/security/graph?view= — 安全图谱 (view: full/attack/cve/compliance) */
export function getSecurityGraph(
  view: 'full' | 'attack' | 'cve' | 'compliance' = 'full',
  opts: { signal?: AbortSignal } = {},
): Promise<SecurityGraphResponse> {
  return getJSON<SecurityGraphResponse>(`/api/security/graph?view=${view}`, {
    signal: opts.signal,
  });
}

// ---------------------------------------------------------------------------
// 合规矩阵 (/api/compliance/*)
// ---------------------------------------------------------------------------

export interface FrameworkMeta {
  id: string;
  name: string;
  description: string;
  control_count: number;
}

export interface ControlItem {
  framework: string;
  control_id: string;
  name: string;
}

export interface MatrixData {
  rows: {
    event_type: string;
    controls: ControlItem[];
  }[];
  columns: ControlItem[];
}

/** GET /api/compliance/frameworks — 合规章程元数据 */
export function getComplianceFrameworks(): Promise<{ frameworks: FrameworkMeta[] }> {
  return getJSON<{ frameworks: FrameworkMeta[] }>('/api/compliance/frameworks');
}

/** GET /api/compliance/matrix?event_types=&frameworks= — 事件类型 × 控制项矩阵 */
export function getComplianceMatrix(
  eventTypes: string[],
  frameworks?: string[],
): Promise<MatrixData> {
  const params = new URLSearchParams();
  if (eventTypes.length) params.set('event_types', eventTypes.join(','));
  if (frameworks?.length) params.set('frameworks', frameworks.join(','));
  return getJSON<MatrixData>(`/api/compliance/matrix?${params.toString()}`);
}

/** GET /api/compliance/controls/{eventType} — 单事件类型适用的控制项 */
export function getComplianceControls(
  eventType: string,
): Promise<{ event_type: string; controls: ControlItem[] }> {
  return getJSON<{ event_type: string; controls: ControlItem[] }>(
    `/api/compliance/controls/${encodeURIComponent(eventType)}`,
  );
}

// ---------------------------------------------------------------------------
// CVE (/api/cve/*)
// ---------------------------------------------------------------------------

export interface AttackTechnique {
  technique_id: string;
  name: string;
  tactic: string;
  count: number;
}

export interface AttackMappingResult {
  techniques: AttackTechnique[];
  total_cves: number;
  matched_cves: number;
}

/** GET /api/cve/attack-mapping?cve_ids= — CVE → ATT&CK 技术映射 (空入参不走网络) */
export function getCveAttackMapping(cveIds: string[]): Promise<AttackMappingResult> {
  if (!cveIds.length) return Promise.resolve({ techniques: [], total_cves: 0, matched_cves: 0 });
  return getJSON<AttackMappingResult>(
    `/api/cve/attack-mapping?cve_ids=${encodeURIComponent(cveIds.join(','))}`,
  );
}

export interface HeatmapData {
  weeks: string[];
  severities: string[];
  matrix: number[][];
}

/** GET /api/cve/heatmap?weeks= — CVE 严重度周热力图 */
export function getCveHeatmap(weeks = 12): Promise<HeatmapData> {
  return getJSON<HeatmapData>(`/api/cve/heatmap?weeks=${weeks}`);
}

// ---------------------------------------------------------------------------
// 实体关联 (/api/security/entities/{id}/related)
// ---------------------------------------------------------------------------

/** GET /api/security/entities/{id}/related?depth= — 实体关联节点 ({nodes}) */
export function getSecurityEntityRelated<T = { nodes?: unknown[] }>(
  entityId: string,
  depth = 1,
): Promise<T> {
  return getJSON<T>(
    `/api/security/entities/${encodeURIComponent(entityId)}/related?depth=${depth}`,
  );
}