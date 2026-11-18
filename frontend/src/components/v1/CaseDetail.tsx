/**
 * CaseDetail — Case 详情 (v0.8.5 C2 自 V1Prototype.tsx 提取为独立组件)
 *
 * 复用方:
 *   - V1Prototype V1Shell (页内选中 case, re-export 保持旧测试 import 路径兼容)
 *   - CaseDetailPage (/cases/:caseId 判断层深链接, spec = docs/v0.8.5/V0.8.5_PLAN.md §5)
 *
 * 区块锚点 (供 ?section= 定位): section-knowledge / section-judgments / section-actions
 * 数据: 真实 API (aggregate 单点拉取 + SSE 精准失效), 失败显 unavailable, 无 mock fallback。
 *
 * B5 续拆 (2026-11-18): 本文件是 **容器** — 状态 + 取数编排 + mutation 编排;
 * 展示区块 (头部 / 走查卡 / 知识 / 证据 / 召回 / 判断 / 行动链) 拆入 ./caseDetail/*, 只收 props。
 * C11 R19.1 契约: 取数只在此处发生 (单点 /aggregate + knowledge 复用统计), 子区块不得自行请求,
 * 否则 1 次退化为 1+N; 旧 N+1 端点 (getCase/listJudgments/listActions/listRuns/listArtifacts) 保持零调用。
 */

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import type { Case, Judgment } from '../../domain/v1_0';
import type { Action, Run, Artifact, Knowledge } from '../../api/v1';
import {
  listKnowledge, getKnowledgeReuse,
  getCaseAggregate,
  type ReuseReceipt, type CaseEvidenceMaterial, type KnowledgeRecallCandidate,
} from '../../api/v1';
import { useSSEAggregateInvalidate } from './useSSEAggregateInvalidate';
import { useToast } from '../Toast';
import { CaseDetailHeader } from './caseDetail/CaseDetailHeader';
import { WalkthroughPathsCard } from './caseDetail/WalkthroughPathsCard';
import { KnowledgeSection } from './caseDetail/KnowledgeSection';
import { EvidenceSection } from './caseDetail/EvidenceSection';
import { RecallKnowledgeSection } from './caseDetail/RecallKnowledgeSection';
import { JudgmentsSection } from './caseDetail/JudgmentsSection';
import { ActionsSection } from './caseDetail/ActionsSection';
import { useCaseDetailMutations } from './caseDetail/useCaseDetailMutations';
import { extractCveId, type ReuseSummary } from './caseDetail/caseDetailModel';

// Badge 实现拆至 ./caseDetail/CaseBadge, 此处 re-export 保持 V1Prototype 旧 import 路径兼容
export { Badge } from './caseDetail/CaseBadge';

export function CaseDetail({ case_, onBack }: { case_: Case; onBack: () => void }) {
  // v1.0 C09 R14 修复: 删 usingFallback state, 失败显 unavailable (AC-11)
  // v1.0 C10 R14/R15 修复: 加 7 mutation 接线 + Toast 反馈 + 失败保留输入 (mutation 编排见 useCaseDetailMutations)
  // v1.0 C11 R18/R19 修复: 单点 GET /api/v1/cases/{id}/aggregate 拉齐 5 类对象,
  //   替代旧 N+1 (getCase + listJudgments + listActions + N×listRuns + N×M×listArtifacts),
  //   同 tab 多 CaseDetail 不再 O(case) 次无效重拉, 按 (case_id+revision) 精确失效.
  const [liveCase, setLiveCase] = useState<Case | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [liveJudgments, setLiveJudgments] = useState<Judgment[]>([]);
  const [judgmentsLoading, setJudgmentsLoading] = useState(false);
  const [liveActions, setLiveActions] = useState<Action[]>([]);
  const [liveRuns, setLiveRuns] = useState<Run[]>([]);
  const [liveArtifacts, setLiveArtifacts] = useState<Artifact[]>([]);
  const [actionChainLoading, setActionChainLoading] = useState(false);
  const [liveEvidence, setLiveEvidence] = useState<CaseEvidenceMaterial[]>([]);
  // D4: 复利卡 (诚实计数 — v1_knowledge_adoptions 真实回执, 不做无基线估算)
  const [reuseSummary, setReuseSummary] = useState<ReuseSummary | null>(null);
  // D3: SK-05 自动召回候选 + 本页已采用集合 (采用回执产生后标记, 不重复采用)
  const [recallCandidates, setRecallCandidates] = useState<KnowledgeRecallCandidate[]>([]);
  const [adoptedRecallIds, setAdoptedRecallIds] = useState<Set<string>>(new Set());
  const [liveKnowledge, setLiveKnowledge] = useState<Knowledge[]>([]);
  const [knowledgeReceipts, setKnowledgeReceipts] = useState<Record<string, ReuseReceipt>>({});
  const [knowledgeLoading, setKnowledgeLoading] = useState(false);
  const toast = useToast();
  // D2 P2 修复 (code-review #5): 聚合响应竞态守卫 — case 切换/深链跳转时,
  // 旧 case 的在途响应不得覆盖新 case 的 state (last-write-wins → 按 generation 丢弃)
  const fetchGenRef = useRef(0);

  // C11 R19: 单点 aggregate 拉取 — 1 次 HTTP 拉齐 case+judgments+actions+runs+artifacts.
  const refetchAggregate = useCallback(async (silent: boolean = false) => {
    const gen = ++fetchGenRef.current;
    setLoading(true);
    setError(null);
    setJudgmentsLoading(true);
    setActionChainLoading(true);
    setKnowledgeLoading(true);
    try {
      const agg = await getCaseAggregate(case_.id, {
        judgments_limit: 50,
        actions_limit: 50,
        runs_per_action: 10,
        artifacts_per_run: 10,
      });
      if (gen !== fetchGenRef.current) return;  // 过期响应 — 已切换 case, 丢弃
      setLiveCase(agg.case);
      setLiveJudgments(agg.judgments);
      setLiveActions(agg.actions);
      setLiveRuns(agg.runs);
      setLiveArtifacts(agg.artifacts);
      setLiveEvidence(agg.evidence_materials ?? []);
      setReuseSummary(agg.reuse_summary ?? null);
      setRecallCandidates(agg.recall_candidates ?? []);
      // knowledge 仍走 listKnowledge (与 reuse receipt), 不在 aggregate 范围
      // (复用统计为派生聚合, 不在主链路 N+1 内, T13 形态保留)
      if (gen !== fetchGenRef.current) return;
      const knResp = await listKnowledge({ case_id: case_.id, limit: 50 });
      setLiveKnowledge(knResp.items);
      const receipts: Record<string, ReuseReceipt> = {};
      // 顺序拉 (复用统计非高频, ≤ 50 条)
      for (const k of knResp.items) {
        try {
          const r = await getKnowledgeReuse(k.id);
          receipts[k.id] = r.receipt;
        } catch {
          // 单条 reuse 拉取失败 → 该条不显 receipt (其他条正常)
        }
      }
      setKnowledgeReceipts(receipts);
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e);
      if (gen !== fetchGenRef.current) return;  // 过期响应
      setError(msg);
      if (!silent) {
        toast.show({ type: 'error', message: `刷新失败: ${msg}` });
      }
    } finally {
      setLoading(false);
      setJudgmentsLoading(false);
      setActionChainLoading(false);
      setKnowledgeLoading(false);
    }
  }, [case_.id, toast]);

  // 初次加载 + case 切换时拉取
  useEffect(() => {
    refetchAggregate(true);
  }, [refetchAggregate]);

  // C11 R18: 按 (case_id+revision) 精确失效 — 5 service outbox 事件触发
  // 同 case 关联的 aggregate_type 变更才 refetch, 避免 T17.5 全局广播式 refetch.
  useSSEAggregateInvalidate({
    currentCaseId: case_.id,
    currentRevision: liveCase?.revision ?? 0,
    onRefetch: () => { void refetchAggregate(true); },
  });

  // C10: 7 mutation 完成后 refetch — 旧 refetchChain 替换为单点 aggregate.
  const refetchChain = useCallback(async (_silent: boolean = false) => {
    await refetchAggregate(true);
  }, [refetchAggregate]);

  const display = liveCase ?? case_;
  // v1.0 C09 R14 修复: 不再 fallback MOCK_*.filter; 真实数据空 → 显空数组
  const judgments: Judgment[] = liveJudgments;
  const actions: Action[] = liveActions;
  const runs: Run[] = liveRuns;
  const artifacts: Artifact[] = liveArtifacts;

  // ── D2: 真实出稿 (SK-02/SK-03) — 证据材料来自 D1.2 立项绑定, 失败如实 DEGRADED ──
  const cveId = useMemo(() => extractCveId(`${display.title} ${display.question}`), [display]);

  // C10 R14/R15 + D2/D3: mutation 编排 (approve/start/cancel/verify/accept/reject/close + 起草/发布/生成/采用)
  const {
    pendingMutation, generating,
    handleCloseCase, handleApproveAction, handleStartAction, handleCancelAction,
    handleVerifyArtifact, handleAcceptArtifact, handleRejectArtifact,
    handleGenerateJudgment, handlePublishJudgment, handleGenerateAction, handleAdoptRecall,
  } = useCaseDetailMutations({
    display,
    judgments,
    evidence: liveEvidence,
    cveId,
    refetchChain,
    onRecallAdopted: (id) => setAdoptedRecallIds(prev => new Set(prev).add(id)),
  });

  // T13: 优先真实 knowledge, 不再 fallback MOCK_KNOWLEDGE.filter
  const knowledgeItems: Knowledge[] = liveKnowledge;

  return (
    <div className="space-y-6">
      <CaseDetailHeader
        display={display}
        loading={loading}
        error={error}
        pendingMutation={pendingMutation}
        onBack={onBack}
        onCloseCase={handleCloseCase}
      />

      <WalkthroughPathsCard actions={actions} runs={runs} artifacts={artifacts} />

      <KnowledgeSection
        items={knowledgeItems}
        receipts={knowledgeReceipts}
        reuseSummary={reuseSummary}
        loading={knowledgeLoading}
      />

      <EvidenceSection materials={liveEvidence} />

      <RecallKnowledgeSection
        candidates={recallCandidates}
        adoptedIds={adoptedRecallIds}
        onAdopt={handleAdoptRecall}
      />

      <JudgmentsSection
        judgments={judgments}
        loading={judgmentsLoading}
        generating={generating}
        evidenceCount={liveEvidence.length}
        pendingMutation={pendingMutation}
        onGenerate={handleGenerateJudgment}
        onPublish={handlePublishJudgment}
      />

      <ActionsSection
        actions={actions}
        runs={runs}
        artifacts={artifacts}
        judgments={judgments}
        loading={actionChainLoading}
        generating={generating}
        pendingMutation={pendingMutation}
        onGenerate={handleGenerateAction}
        onApprove={handleApproveAction}
        onStart={handleStartAction}
        onCancel={handleCancelAction}
        onVerify={handleVerifyArtifact}
        onAccept={handleAcceptArtifact}
        onReject={handleRejectArtifact}
      />
    </div>
  );
}
