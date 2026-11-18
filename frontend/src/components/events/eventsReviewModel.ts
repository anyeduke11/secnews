/**
 * eventsReviewModel — 通稿审核 (EventsReviewPage) 的纯类型
 * (B5.6 拆分: 自 EventsReviewPage.tsx 原样提取)
 *
 * 纪律: 只放无 React 依赖的类型; 取数编排与状态全部留在 EventsReviewPage 容器,
 *       纯展示区块见同目录 EventsReviewBlocks.tsx。
 */

/** 事件类型行 (GET /api/event-technique/event-types 的 items 元素) */
export interface EventTypeRow {
  id: string;
  name?: string;
  candidate_stats?: {
    pending?: number;
    approved?: number;
    rejected?: number;
    total?: number;
    avg_confidence?: number;
  };
}

/** 候选行 (GET /api/event-technique/candidates 的 items 元素) */
export interface CandidateRow {
  id: string;
  technique_id: string;
  stage?: string;
  confidence?: number;
  evidence_quote?: string;
  rationale?: string;
  owner_status?: string;
}

/** 操作结果提示 (容器维护的横幅态) */
export interface ReviewNotice {
  kind: 'ok' | 'err';
  text: string;
}
