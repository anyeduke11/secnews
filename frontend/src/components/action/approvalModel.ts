/**
 * approvalModel — 审批收件箱 (ApprovalInbox) 的类型 / 常量 / 纯函数 (B5 从 ApprovalInbox 抽出)
 *
 * 只放无 React 依赖的内容; 展示区块见 ApprovalDraftCard.tsx / ApprovalFailedList.tsx /
 * ApprovalBadge.tsx, 取数与刷新编排仍归容器 ApprovalInbox.tsx。
 */
import type { Proposal, ProposalKind } from '../../api/proposals';

/** 后端 MAX_REJECT_REASON_CHARS, 前端先挡一道 (后端 400 兜底)。 */
export const MAX_REJECT_REASON = 200;
/** 单机工作站单用户, 与既有 v1 端点 submitted_by='user'/'owner' 口径一致。 */
export const REVIEWER = 'owner';
/** 批准即产生真实写入 (产物落盘 / 知识写库) 的类型 — 橙色写操作标记。 */
export const WRITE_KINDS: ReadonlySet<ProposalKind> = new Set(['judgment_draft', 'knowledge_draft']);

export const KIND_LABEL: Record<ProposalKind, string> = {
  judgment_draft: '研判草案',
  case_suggestion: '建案建议',
  knowledge_draft: '知识草案',
  report: '报告',
};

export const SOURCE_LABEL: Record<Proposal['source'], string> = {
  agent: 'AI 代理',
  command: '命令栏',
  copilot: '副驾',
};

export type CardBusy = 'approve' | 'reject' | 'retry';

export function fmtTime(iso?: string | null): string {
  if (!iso) return '';
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? '' : d.toLocaleString('zh-CN', { hour12: false });
}

/** 研判草案正文首行 (claim); 其余类型回退到 payload JSON 预览。 */
export function payloadPreview(p: Proposal): string {
  const claim = p.payload?.claim;
  if (typeof claim === 'string' && claim.trim()) return claim;
  try {
    return JSON.stringify(p.payload ?? {}, null, 2);
  } catch {
    return String(p.payload ?? '');
  }
}
