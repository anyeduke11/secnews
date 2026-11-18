/**
 * caseDetailModel — CaseDetail 纯类型 / 纯函数 (B5 续拆: 自 CaseDetail.tsx 原样提取)
 *
 * 纪律: 只做无副作用派生, 不取数、不持有状态 (取数编排全留在 CaseDetail 容器)。
 */
import type { Action, Run, Artifact } from '../../../api/v1';

/** aggregate.reuse_summary (D4 复利卡: v1_knowledge_adoptions 真实回执计数) */
export interface ReuseSummary {
  adoptions_total: number;
  adoptions_30d: number;
  distinct_knowledge: number;
}

/** 走查 3 路径标记 (T12 强化: 显式呈现 3 路径而非简单色块) */
export interface WalkthroughFlags {
  hasMissingAssets: boolean;
  hasFailure: boolean;
  hasPendingAcceptance: boolean;
  hasRejected: boolean;
}

export function walkthroughFlags(actions: Action[], runs: Run[], artifacts: Artifact[]): WalkthroughFlags {
  return {
    hasMissingAssets: actions.length > 0 && artifacts.length === 0,
    hasFailure: runs.some(r => r.status === 'failed'),
    hasPendingAcceptance: artifacts.some(a => a.status === 'verified'),
    hasRejected: artifacts.some(a => a.status === 'rejected'),
  };
}

/** D2: 从 case 标题 + 问题文本解析 CVE 编号 (SK-03 inspection-materials 入参) */
export function extractCveId(text: string): string {
  return (/\bCVE-\d{4}-\d{4,7}\b/i.exec(text)?.[0] ?? '').toUpperCase();
}
