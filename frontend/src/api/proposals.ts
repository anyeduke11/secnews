/**
 * 提案审批客户端 (v0.8.6 P1-1/M1, 后端 backend/api/run_ledger_api.py)。
 *
 * 人主律链路: AI 起草 → proposal(draft) → /action 审批收件箱 →
 * 人批准 (双签 Run + 产物) / 驳回 (必填原因)。模型失败回 status=failed。
 */
import { getJSON, postJSON } from '../lib/api';

export type ProposalSource = 'agent' | 'command' | 'copilot';
export type ProposalKind =
  | 'judgment_draft' | 'case_suggestion' | 'knowledge_draft' | 'report';
export type ProposalStatus =
  | 'draft' | 'approved' | 'rejected' | 'expired' | 'failed';

/** 与后端 run_ledger_service/proposal_repo 行字典对齐 (JSON 列已解析)。 */
export interface Proposal {
  id: string;
  case_id: string | null;
  source: ProposalSource;
  kind: ProposalKind;
  payload: Record<string, unknown>;
  evidence_ids: string[];
  prompt_version: string | null;
  status: ProposalStatus;
  error_msg: string | null;
  reject_reason: string | null;
  reviewed_by: string | null;
  reviewed_at: string | null;
  run_id: string | null;
  created_at?: string;
}

export interface ProposalListResponse {
  items: Proposal[];
  total: number;
  filter: { status: string | null; kind: string | null };
}

/** GET /api/proposals — 收件箱列表 (按状态/类型过滤)。 */
export function listProposals(params: {
  status?: ProposalStatus;
  kind?: ProposalKind;
  limit?: number;
  offset?: number;
} = {}): Promise<ProposalListResponse> {
  const qs = new URLSearchParams();
  if (params.status) qs.set('status', params.status);
  if (params.kind) qs.set('kind', params.kind);
  if (params.limit != null) qs.set('limit', String(params.limit));
  if (params.offset != null) qs.set('offset', String(params.offset));
  const suffix = qs.toString();
  return getJSON<ProposalListResponse>(`/api/proposals${suffix ? `?${suffix}` : ''}`);
}

/** POST /api/proposals/draft-judgment — Case 页 AI 起草研判。
 * 成功回 draft 提案; 模型超时/拒绝回 **同 200 + status=failed** (由调用方区分)。 */
export function draftJudgment(caseId: string): Promise<Proposal> {
  return postJSON<Proposal>('/api/proposals/draft-judgment', { case_id: caseId });
}

/** 副驾三卡起草 kind (M3; judgment 走 draftJudgment 专用端点)。 */
export type CopilotDraftKind = 'case_suggestion' | 'knowledge_draft' | 'report';

/** POST /api/proposals/copilot-draft — 副驾卡起草 (P1-3 M3)。
 * case_suggestion/report 需 case_id; knowledge_draft 需 knowledge_id。
 * 失败语义同 draftJudgment: HTTP 200 + status=failed。 */
export function copilotDraft(
  kind: CopilotDraftKind,
  ctx: { case_id?: string; knowledge_id?: string },
): Promise<Proposal> {
  return postJSON<Proposal>('/api/proposals/copilot-draft', { kind, ...ctx });
}

/** POST /api/proposals/{id}/approve — 人批准; editedPayload 非空 = 修订后批准。 */
export function approveProposal(
  id: string,
  reviewedBy: string,
  editedPayload?: Record<string, unknown>,
): Promise<Proposal> {
  return postJSON<Proposal>(
    `/api/proposals/${encodeURIComponent(id)}/approve`,
    editedPayload != null ? { reviewed_by: reviewedBy, payload: editedPayload }
      : { reviewed_by: reviewedBy },
  );
}

/** POST /api/proposals/{id}/reject — 人驳回 (reason 必填 ≤200, 后端 400 兜底)。 */
export function rejectProposal(
  id: string,
  reviewedBy: string,
  reason: string,
): Promise<Proposal> {
  return postJSON<Proposal>(
    `/api/proposals/${encodeURIComponent(id)}/reject`,
    { reviewed_by: reviewedBy, reason },
  );
}
