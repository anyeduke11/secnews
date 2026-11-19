/**
 * useCaseDetailMutations — CaseDetail 容器 mutation 编排 (B5 续拆: 自 CaseDetail.tsx 原样搬运)
 *
 * v1.0 C10 R14/R15: 7 mutation (approve / start / cancel / verify / accept / reject / closeCase)
 *   + 发布判断 / AI 起草研判 / SK-03 生成行动 / SK-05 采用召回。
 * 纪律: 全部走 allowed_actions 守卫, 失败 Toast.error (Mimosa 禁 silent), 成功 Toast.success + refetch;
 *       本 hook 不发任何聚合取数请求 — 重拉一律走容器注入的 refetchChain (单点 /aggregate)。
 */
import { useState } from 'react';
import type { Case, Judgment } from '../../../domain/v1_0';
import type { Action, Artifact, CaseEvidenceMaterial, KnowledgeRecallCandidate } from '../../../api/v1';
import {
  approveAction, startAction, cancelAction, verifyArtifact, acceptArtifact, rejectArtifact, closeCase,
  generateAction, publishJudgment, adoptKnowledge,
} from '../../../api/v1';
import { draftJudgment } from '../../../api/proposals';
import { useToast } from '../../../primitives/Toast';

export interface CaseDetailMutationDeps {
  /** liveCase ?? case_ (容器派生) */
  display: Case;
  judgments: Judgment[];
  evidence: CaseEvidenceMaterial[];
  cveId: string;
  /** 容器单点 aggregate 重拉 (mutation 成功后调用) */
  refetchChain: (silent?: boolean) => Promise<void>;
  /** SK-05 采用成功后标记本页已采用集合 (状态归容器, 避免重复采用) */
  onRecallAdopted: (id: string) => void;
}

export function useCaseDetailMutations({
  display, judgments, evidence, cveId, refetchChain, onRecallAdopted,
}: CaseDetailMutationDeps) {
  const toast = useToast();
  const [pendingMutation, setPendingMutation] = useState<string | null>(null);
  const [generating, setGenerating] = useState<"judgment" | "action" | null>(null);

  const runMutation = async <T,>(
    key: string,
    op: () => Promise<T>,
    successMsg: string,
    errorPrefix: string,
  ): Promise<T | null> => {
    setPendingMutation(key);
    try {
      const result = await op();
      toast.show({ type: 'success', message: successMsg });
      await refetchChain(true);
      return result;
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e);
      toast.show({ type: 'error', message: `${errorPrefix}: ${msg}` });
      return null;  // 失败保留输入 — 不抛, 不冒充成功
    } finally {
      setPendingMutation(null);
    }
  };

  const handleApproveAction = (a: Action) => runMutation(
    `approve:${a.id}`,
    () => approveAction(a.id, { expected_revision: a.revision }).then(r => r.item),
    `行动已批准: ${a.title}`,
    '批准失败',
  );
  const handleStartAction = (a: Action) => runMutation(
    `start:${a.id}`,
    () => startAction(a.id, {
      expected_revision: a.revision,
      idempotency_key: `idem_${a.id}_${Date.now()}`,
      protocol: 'pi',
      trigger_source: 'user',
    }).then(r => r.run ?? r),
    `行动已启动: ${a.title}`,
    '启动失败',
  );
  const handleCancelAction = (a: Action) => runMutation(
    `cancel:${a.id}`,
    () => cancelAction(a.id, { expected_revision: a.revision }).then(r => r.item),
    `行动已取消: ${a.title}`,
    '取消失败',
  );
  const handleVerifyArtifact = (art: Artifact) => runMutation(
    `verify:${art.id}`,
    () => verifyArtifact(art.id, { expected_revision: art.revision, verified_result: 'pass', verified_by: 'user' }),
    `产物已验证: ${art.title}`,
    '验证失败',
  );
  const handleAcceptArtifact = (art: Artifact) => runMutation(
    `accept:${art.id}`,
    () => acceptArtifact(art.id, { expected_revision: art.revision, accepted_by: 'user' }),
    `产物已业务验收: ${art.title}`,
    '验收失败',
  );
  const handleRejectArtifact = (art: Artifact) => runMutation(
    `reject:${art.id}`,
    () => rejectArtifact(art.id, { expected_revision: art.revision, rejected_by: 'user', reason: '人工拒绝 (UI 入口)' }),
    `产物已拒绝: ${art.title}`,
    '拒绝失败',
  );
  const handleCloseCase = () => {
    if (!display.allowed_actions?.includes('close' as any)) {
      toast.show({ type: 'warning', message: '当前事项不可关闭 (allowed_actions 不含 close)' });
      return;
    }
    runMutation(
      `close:${display.id}`,
      () => closeCase(display.id, { expected_revision: display.revision ?? 1 }).then(r => r.item),
      `事项已关闭: ${display.title}`,
      '关闭失败 (R17: 需全 action 终态 + 无 active run + ≥1 verified artifact + ≥1 published judgment)',
    );
  };

  // v0.8.6 P1-1/M1: 「AI 起草研判」走提案审批流 — HEAVY 档草案落 v1_proposals(draft),
  // 人在 /action 审批收件箱批准后才双签 Run + 产物; 模型失败回 failed 提案可重试。
  const handleGenerateJudgment = async () => {
    if (evidence.length === 0) {
      toast.show({ type: 'warning', message: '暂无证据材料 — 请先从资料层信号立项携带证据 (M1: 研判必须带证据引用)' });
      return;
    }
    setGenerating('judgment');
    try {
      const proposal = await draftJudgment(display.id);
      if (proposal.status === 'failed') {
        toast.show({ type: 'error', message: `AI 起草失败: ${proposal.error_msg || '模型未返回'} — 可在「行动」菜单审批收件箱重试` });
      } else {
        toast.show({ type: 'success', message: '研判草案已送入「行动」菜单审批收件箱 — 人工批准后生成产物' });
      }
    } catch (e) {
      toast.show({ type: 'error', message: `起草失败: ${e instanceof Error ? e.message : String(e)}` });
    } finally {
      setGenerating(null);
    }
  };

  const handlePublishJudgment = (j: Judgment) => runMutation(
    `publish:${j.id}`,
    () => publishJudgment(j.id, { expected_revision: j.revision ?? 1 }),
    `判断已发布 (${j.claim_type})`,
    '发布失败',
  );

  const handleGenerateAction = async () => {
    const published = judgments.find(j => j.status === 'published');
    if (!published) {
      toast.show({ type: 'warning', message: '需先有 published 判断 (§10.1: 行动必须引用已发布判断)' });
      return;
    }
    if (!cveId) {
      toast.show({ type: 'error', message: 'case 未解析出 CVE 编号 — SK-03 为 inspection-materials 能力' });
      return;
    }
    setGenerating('action');
    try {
      await generateAction({
        case_id: display.id,
        judgment_id: published.id,
        title: `排查材料: ${display.title}`.slice(0, 200),
        subject_name: (evidence[0]?.title || display.title).slice(0, 200),
        cve_id: cveId,
        scope: display.question.slice(0, 2000),
        evidence_materials: evidence.map(m => ({ id: m.id, title: m.title ?? '', content_hash: m.content_hash })),
        submitted_by: 'user',
      });
      toast.show({ type: 'success', message: '行动已生成 (planned) — 批准后执行' });
      await refetchChain(true);
    } catch (e) {
      toast.show({ type: 'error', message: `生成失败 (真实出稿依赖 dsh/ai_hub): ${e instanceof Error ? e.message : String(e)}` });
    } finally {
      setGenerating(null);
    }
  };

  // D3: SK-05 采用 — case 页发起, case_id 自动携带 (免手填 ULID), 产生真实采用回执
  const handleAdoptRecall = async (k: KnowledgeRecallCandidate) => {
    try {
      await adoptKnowledge(k.id, {
        case_id: display.id,
        decision: 'adopted',
        condition_diff: [],
        decided_by: 'user',
      });
      toast.show({ type: 'success', message: '已采用 — 采用回执已记录' });
      onRecallAdopted(k.id);
      await refetchChain(true);
    } catch (e) {
      toast.show({ type: 'error', message: `采用失败: ${e instanceof Error ? e.message : String(e)}` });
    }
  };

  return {
    pendingMutation,
    generating,
    handleCloseCase,
    handleApproveAction,
    handleStartAction,
    handleCancelAction,
    handleVerifyArtifact,
    handleAcceptArtifact,
    handleRejectArtifact,
    handleGenerateJudgment,
    handlePublishJudgment,
    handleGenerateAction,
    handleAdoptRecall,
  };
}
