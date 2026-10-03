/**
 * CaseDetail — Case 详情 (v0.8.5 C2 自 V1Prototype.tsx 提取为独立组件)
 *
 * 复用方:
 *   - V1Prototype V1Shell (页内选中 case, re-export 保持旧测试 import 路径兼容)
 *   - CaseDetailPage (/cases/:caseId 判断层深链接, spec = docs/v0.8.5/V0.8.5_PLAN.md §5)
 *
 * 区块锚点 (供 ?section= 定位): section-knowledge / section-judgments / section-actions
 * 数据: 真实 API (aggregate 单点拉取 + SSE 精准失效), 失败显 unavailable, 无 mock fallback。
 */

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import type { Case, Judgment } from '../../domain/v1_0';
import type { Action, Run, Artifact, Knowledge } from '../../api/v1';
import {
  listKnowledge, getKnowledgeReuse,
  getCaseAggregate,
  approveAction, startAction, cancelAction, verifyArtifact, acceptArtifact, rejectArtifact, closeCase,
  generateAction, publishJudgment,
  adoptKnowledge,
  type ReuseReceipt, type CaseEvidenceMaterial, type KnowledgeRecallCandidate,
} from '../../api/v1';
import { draftJudgment } from '../../api/proposals';
import { renderInlineMarkdown } from '../../lib/markdown';
import { useSSEAggregateInvalidate } from './useSSEAggregateInvalidate';
import { useToast } from '../Toast';

// v1.0.1 一致性重构: Badge 改用 CSS 变量 token (light/dark 双值), 背景用 color-mix 表达 dim 透明层.
export function Badge({ children, color }: { children: React.ReactNode; color: 'green' | 'red' | 'yellow' | 'gray' | 'blue' }) {
  const styles: Record<string, { bg: string; fg: string }> = {
    green:  { bg: 'color-mix(in srgb, var(--color-success) 14%, transparent)', fg: 'var(--color-success)' },
    red:    { bg: 'color-mix(in srgb, var(--color-error)   14%, transparent)', fg: 'var(--color-error)' },
    yellow: { bg: 'color-mix(in srgb, var(--color-warning) 14%, transparent)', fg: 'var(--color-warning)' },
    gray:   { bg: 'color-mix(in srgb, var(--text-muted)   14%, transparent)', fg: 'var(--text-secondary)' },
    blue:   { bg: 'color-mix(in srgb, var(--color-info)    14%, transparent)', fg: 'var(--color-info)' },
  };
  const s = styles[color] || styles.gray;
  return (
    <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium" style={{ background: s.bg, color: s.fg }}>
      {children}
    </span>
  );
}

export function CaseDetail({ case_, onBack }: { case_: Case; onBack: () => void }) {
  // v1.0 C09 R14 修复: 删 usingFallback state, 失败显 unavailable (AC-11)
  // v1.0 C10 R14/R15 修复: 加 7 mutation 接线 + Toast 反馈 + 失败保留输入
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
  const [reuseSummary, setReuseSummary] = useState<{ adoptions_total: number; adoptions_30d: number; distinct_knowledge: number } | null>(null);
  // D3: SK-05 自动召回候选 + 本页已采用集合 (采用回执产生后标记, 不重复采用)
  const [recallCandidates, setRecallCandidates] = useState<KnowledgeRecallCandidate[]>([]);
  const [adoptedRecallIds, setAdoptedRecallIds] = useState<Set<string>>(new Set());
  const [liveKnowledge, setLiveKnowledge] = useState<Knowledge[]>([]);
  const [knowledgeReceipts, setKnowledgeReceipts] = useState<Record<string, ReuseReceipt>>({});
  const [knowledgeLoading, setKnowledgeLoading] = useState(false);
  const [pendingMutation, setPendingMutation] = useState<string | null>(null);
  const [generating, setGenerating] = useState<"judgment" | "action" | null>(null);
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

  // C10 R14/R15: 7 mutation handlers (approve / start / cancel / verify / accept / reject / closeCase)
  // 全部走 allowed_actions 守卫, 失败 Toast.error (Mimosa 禁 silent), 成功 Toast.success + refetch
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

  const display = liveCase ?? case_;
  // v1.0 C09 R14 修复: 不再 fallback MOCK_*.filter; 真实数据空 → 显空数组
  const judgments: Judgment[] = liveJudgments;
  const actions: Action[] = liveActions;
  const runs: Run[] = liveRuns;
  const artifacts: Artifact[] = liveArtifacts;

  // ── D2: 真实出稿 (SK-02/SK-03) — 证据材料来自 D1.2 立项绑定, 失败如实 DEGRADED ──
  const cveId = useMemo(
    () => (/\bCVE-\d{4}-\d{4,7}\b/i.exec(`${display.title} ${display.question}`)?.[0] ?? "").toUpperCase(),
    [display],
  );

  // v0.8.6 P1-1/M1: 「AI 起草研判」走提案审批流 — HEAVY 档草案落 v1_proposals(draft),
  // 人在 /action 审批收件箱批准后才双签 Run + 产物; 模型失败回 failed 提案可重试。
  const handleGenerateJudgment = async () => {
    if (liveEvidence.length === 0) {
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
        subject_name: (liveEvidence[0]?.title || display.title).slice(0, 200),
        cve_id: cveId,
        scope: display.question.slice(0, 2000),
        evidence_materials: liveEvidence.map(m => ({ id: m.id, title: m.title ?? '', content_hash: m.content_hash })),
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
      setAdoptedRecallIds(prev => new Set(prev).add(k.id));
      await refetchChain(true);
    } catch (e) {
      toast.show({ type: 'error', message: `采用失败: ${e instanceof Error ? e.message : String(e)}` });
    }
  };


  // 走查 3 路径检测 (T12 强化: 显式呈现 3 路径而非简单色块)
  const hasMissingAssets = actions.length > 0 && artifacts.length === 0;
  const hasFailure = runs.some(r => r.status === 'failed');
  const hasPendingAcceptance = artifacts.some(a => a.status === 'verified');
  const hasRejected = artifacts.some(a => a.status === 'rejected');
  // T13: 优先真实 knowledge, 不再 fallback MOCK_KNOWLEDGE.filter
  const knowledgeItems: Knowledge[] = liveKnowledge;

  return (
    <div className="space-y-6">
      {/* 头部 */}
      <div className="flex items-start justify-between">
        <div>
          <button onClick={onBack} className="text-sm mb-2" style={{ color: 'var(--text-muted)' }}>← 返回事项列表</button>
          <h2 className="text-xl font-bold" style={{ color: 'var(--text-primary)' }}>{display.title}</h2>
          <div className="text-sm mt-1" style={{ color: 'var(--text-muted)' }}>{display.question}</div>
          <div className="text-xs font-mono mt-1" style={{ color: 'var(--text-muted)' }}>
            {display.id} · rev {display.revision}
            {display.reason && ` · ${display.reason}`}
          </div>
        </div>
        <div className="flex gap-2 items-center">
          <Badge color={display.status === 'open' ? 'blue' : display.status === 'in_progress' ? 'green' : display.status === 'blocked' ? 'yellow' : 'gray'}>{display.status}</Badge>
          <Badge color={display.priority === 'p0' ? 'red' : display.priority === 'p1' ? 'yellow' : 'gray'}>{display.priority}</Badge>
          {/* C10 R14/R17: close 按钮 (走 allowed_actions 守卫, R17 4 守卫后端已落) */}
          {display.allowed_actions?.includes('close' as any) && (
            <button
              onClick={handleCloseCase}
              disabled={pendingMutation === `close:${display.id}`}
              className="text-xs px-3 py-1.5 rounded font-medium focus-ring disabled:opacity-50"
              style={{ background: 'var(--color-warning)', color: 'var(--text-on-warning, #fff)' }}
              data-testid="close-case-btn"
            >
              {pendingMutation === `close:${display.id}` ? '关闭中…' : '关闭事项'}
            </button>
          )}
        </div>
      </div>

      {/* T08 加载 / 错误 / fallback 提示 */}
      {loading && (
        <div className="p-3 rounded-lg border text-sm" style={{ background: 'var(--bg-muted)', borderColor: 'var(--line)', color: 'var(--text-muted)' }}>
          加载中...
        </div>
      )}
      {error && !loading && (
        <div className="p-3 rounded-lg border text-sm" style={{ background: 'var(--bg-warning)', borderColor: 'var(--color-warning)', color: 'var(--color-warning)' }}>
          API 调用失败, 显示列表缓存数据: {error}
        </div>
      )}
      {!loading && !error && (
        <div className="p-3 rounded-lg border text-sm" style={{ background: 'var(--bg-card)', borderColor: 'var(--line)', color: 'var(--text-muted)' }}>
          已加载后端数据 · revision {display.revision} · allowed_actions: {display.allowed_actions?.join(', ') || '(none)'}
        </div>
      )}

      {/* 走查 3 路径指示器 (T12 强化: 显式呈现) */}
      <div className="p-3 rounded-lg border" style={{ background: 'var(--bg-muted)', borderColor: 'var(--line)' }}>
        <div className="flex items-center gap-3 flex-wrap">
          <span className="text-sm font-medium" style={{ color: 'var(--text-primary)' }}>走查 3 路径:</span>
          {hasMissingAssets && <Badge color="yellow">缺资产 (材料生成 ≠ 排查完成)</Badge>}
          {hasPendingAcceptance && <Badge color="blue">待验收</Badge>}
          {hasFailure && <Badge color="red">失败</Badge>}
          {hasRejected && <Badge color="red">已拒绝 (防重传蒙混 §8.3)</Badge>}
          {!hasMissingAssets && !hasPendingAcceptance && !hasFailure && !hasRejected && (
            <span className="text-sm" style={{ color: 'var(--text-muted)' }}>无异常</span>
          )}
        </div>
        <div className="text-xs mt-2" style={{ color: 'var(--text-muted)' }}>
          {actions.length} 个行动 · {runs.length} 次运行 · {artifacts.length} 个产物
          {artifacts.filter(a => a.status === 'accepted').length > 0 && ` · ${artifacts.filter(a => a.status === 'accepted').length} 已业务验收`}
        </div>
      </div>

      {/* T13: 知识 (Knowledge) — 复用 + 复查 */}
      <div id="section-knowledge" className="p-4 rounded-lg border" style={{ background: 'var(--bg-card)', borderColor: 'var(--line)' }}>
        <div className="flex items-center justify-between mb-2">
          <h3 className="font-semibold" style={{ color: 'var(--text-primary)' }}>
            知识 (Knowledge) {knowledgeLoading && <span className="text-xs font-normal" style={{ color: 'var(--text-muted)' }}>加载中…</span>}
          </h3>
        </div>
        {/* D4: 复利卡 — 真实回执计数, 不做无基线的「节省 X」估算 */}
        {reuseSummary && reuseSummary.adoptions_total > 0 && (
          <div className="text-xs p-2 rounded mb-3" style={{ background: 'color-mix(in srgb, var(--color-success) 10%, transparent)', color: 'var(--text-secondary)' }} data-testid="reuse-summary-card">
            复利 (真实回执)：本事项已采用知识 <b style={{ color: 'var(--color-success)' }}>{reuseSummary.adoptions_total}</b> 次
            （近 30 天 {reuseSummary.adoptions_30d} · 涉及 {reuseSummary.distinct_knowledge} 个知识条目）
            —— 计数来自 adoption 回执，非估算值
          </div>
        )}
        {knowledgeItems.length === 0 ? (
          <div className="text-sm" style={{ color: 'var(--text-muted)' }}>暂无知识 (SK-04 publish 后出现)</div>
        ) : (
          <div className="space-y-3">
            {knowledgeItems.map(k => {
              const receipt = knowledgeReceipts[k.id];
              return (
                <div key={k.id} className="p-3 rounded border" style={{ borderColor: 'var(--line)' }}>
                  <div className="flex items-center gap-2 mb-2">
                    <span className="font-medium" style={{ color: 'var(--text-primary)' }}>{k.title}</span>
                    <Badge color={k.status === 'published' ? 'green' : k.status === 'draft' ? 'yellow' : k.status === 'deprecated' ? 'gray' : 'red'}>{k.status}</Badge>
                    <span className="text-xs" style={{ color: 'var(--text-muted)' }}>{k.kind} · rev {k.revision}</span>
                  </div>
                  <div className="text-xs font-mono mb-2" style={{ color: 'var(--text-muted)' }}>
                    {k.id} · content_hash: {k.content_hash?.slice(0, 12) ?? '-'}…
                    {k.review_at && ` · 复查: ${k.review_at.slice(0, 10)}`}
                  </div>
                  {/* 前提 (SK-04 必填 ≥1) + 反例 */}
                  {k.prerequisites && k.prerequisites.length > 0 && (
                    <div className="text-xs mt-1" style={{ color: 'var(--text-muted)' }}>
                      前提: {k.prerequisites.join('; ')}
                    </div>
                  )}
                  {k.counter_examples && k.counter_examples.length > 0 && (
                    <div className="text-xs mt-1" style={{ color: 'var(--color-warning)' }}>
                      反例: {k.counter_examples.join('; ')}
                    </div>
                  )}
                  {/* 复用记录 (C12 R16.5: 只数 adoptions, derived_from 不计) */}
                  {receipt && (
                    <div className="text-xs mt-2 p-2 rounded" style={{ background: 'var(--bg-muted)', color: 'var(--text-muted)' }}>
                      采用: total={receipt.total}
                      {Object.keys(receipt.by_decision || {}).length > 0 && (
                        <> · 决策 {JSON.stringify(receipt.by_decision)}</>
                      )}
                      {Object.keys(receipt.by_outcome || {}).length > 0 && (
                        <> · 结果 {JSON.stringify(receipt.by_outcome)}</>
                      )}
                      · 近 30 天 {receipt.recent_30d}
                    </div>
                  )}
                  {/* body 摘要 (Markdown 渲染) */}
                  {k.body && (
                    <details className="mt-2">
                      <summary className="text-xs cursor-pointer" style={{ color: 'var(--text-muted)' }}>查看 body</summary>
                      <div
                        className="text-xs mt-1 p-2 rounded prose-sm"
                        style={{ background: 'var(--bg-muted)', color: 'var(--text-primary)' }}
                        dangerouslySetInnerHTML={{ __html: renderInlineMarkdown(k.body.slice(0, 500)) }}
                      />
                    </details>
                  )}
                </div>
              );
            })}
          </div>
        )}
      </div>

      {/* D1.2: 证据材料 (立项携带 — v1_case_materials 绑定, SK-02 evidence 输入端) */}
      <div id="section-evidence" className="p-4 rounded-lg border" style={{ background: 'var(--bg-card)', borderColor: 'var(--line)' }}>
        <h3 className="font-semibold mb-3" style={{ color: 'var(--text-primary)' }}>
          证据 (Evidence){' '}
          <span className="text-xs font-normal" style={{ color: 'var(--text-muted)' }}>
            {liveEvidence.length} 条 · 来自立项信号 · SK-02 evidence 输入
          </span>
        </h3>
        {(liveEvidence ?? []).length === 0 ? (
          <div className="text-sm" style={{ color: 'var(--text-muted)' }}>
            暂无证据材料 (从资料层信号立项时自动携带)
          </div>
        ) : (
          <div className="space-y-2">
            {(liveEvidence ?? []).map(m => (
              <div key={m.id} className="flex items-start justify-between gap-3 p-3 rounded border" style={{ borderColor: 'var(--line)' }}>
                <div className="flex-1 min-w-0">
                  <div className="text-sm font-medium truncate">
                    {m.url ? (
                      <a href={m.url} target="_blank" rel="noopener noreferrer" style={{ color: 'var(--text-primary)' }}>{m.title}</a>
                    ) : (
                      <span style={{ color: 'var(--text-primary)' }}>{m.title}</span>
                    )}
                  </div>
                  <div className="text-xs mt-1 font-mono" style={{ color: 'var(--text-muted)' }}>
                    {m.id} · hash: {m.content_hash?.slice(0, 12) ?? '-'}…{m.signal_id ? ` · 信号 ${m.signal_id.slice(0, 8)}…` : ''}
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* D3: SK-05 自动召回 — 同类经验自动浮现, 采用免手填 (复利飞轮传动) */}
      {recallCandidates.length > 0 && (
        <div className="p-4 rounded-lg border" style={{ background: 'color-mix(in srgb, var(--color-info) 6%, transparent)', borderColor: 'var(--line)' }}>
          <div className="flex flex-wrap items-center justify-between gap-2 mb-3">
            <h3 className="font-semibold" style={{ color: 'var(--text-primary)' }}>
              召回知识 (SK-05 自动){' '}
              <span className="text-xs font-normal" style={{ color: 'var(--text-muted)' }}>
                {recallCandidates.length} 条 · 按本事项文本匹配 · 采用后产生回执
              </span>
            </h3>
          </div>
          <ul className="space-y-2">
            {recallCandidates.map(k => {
              const adopted = adoptedRecallIds.has(k.id);
              return (
                <li key={k.id} className="flex items-start justify-between gap-3 p-3 rounded border" style={{ borderColor: 'var(--line)' }}>
                  <div className="flex-1 min-w-0">
                    <div className="text-sm font-medium" style={{ color: 'var(--text-primary)' }}>{k.title}</div>
                    <div className="text-xs mt-1" style={{ color: 'var(--text-muted)' }}>
                      {k.kind} · {k.reasons.join('；')}
                    </div>
                  </div>
                  {adopted ? (
                    <Badge color="green">已采用 ✓</Badge>
                  ) : (
                    <button
                      type="button"
                      onClick={() => handleAdoptRecall(k)}
                      className="text-xs px-2.5 py-1 rounded font-medium focus-ring shrink-0"
                      style={{ background: 'var(--color-success)', color: 'var(--text-on-success, #fff)' }}
                      data-testid="recall-adopt-btn"
                    >
                      采用
                    </button>
                  )}
                </li>
              );
            })}
          </ul>
        </div>
      )}

      {/* 判断 */}
      <div id="section-judgments" className="p-4 rounded-lg border" style={{ background: 'var(--bg-card)', borderColor: 'var(--line)' }}>
        <div className="flex flex-wrap items-center justify-between gap-2 mb-3">
          <h3 className="font-semibold" style={{ color: 'var(--text-primary)' }}>
            判断 (Judgment) {judgmentsLoading && <span className="text-xs font-normal" style={{ color: 'var(--text-muted)' }}>加载中…</span>}
          </h3>
          {/* v0.8.6 M1: AI 起草研判 → 提案送审 (/action 收件箱); 证据来自 D1.2 立项绑定 */}
          <button
            type="button"
            onClick={handleGenerateJudgment}
            disabled={generating !== null || liveEvidence.length === 0}
            title={liveEvidence.length === 0 ? '需先携带证据材料 (从信号立项)' : 'HEAVY 档生成研判草案, 送行动菜单审批收件箱'}
            className="text-xs px-3 py-1.5 rounded font-medium focus-ring disabled:opacity-50"
            style={{ background: 'var(--color-info)', color: 'var(--text-on-info, #fff)' }}
            data-testid="generate-judgment-btn"
          >
            {generating === 'judgment' ? '起草中…' : 'AI 起草研判'}
          </button>
        </div>
        {judgments.length === 0 ? (
          <div className="text-sm" style={{ color: 'var(--text-muted)' }}>暂无判断</div>
        ) : (
          <div className="space-y-3">
            {judgments.map(j => (
              <div key={j.id} className="p-3 rounded border" style={{ borderColor: 'var(--line)' }}>
                <div className="flex items-center gap-2 mb-2">
                  <Badge color={j.status === 'published' ? 'green' : j.status === 'draft' ? 'yellow' : 'gray'}>{j.status}</Badge>
                  <span className="text-xs" style={{ color: 'var(--text-muted)' }}>
                    {j.claim_type} · confidence: {j.confidence} · rev {j.revision}
                  </span>
                  {/* D2: draft → 人工发布 (三重守卫, allowed_actions 守卫) */}
                  {j.status === 'draft' && Array.isArray(j.allowed_actions) && j.allowed_actions.includes('publish') && (
                    <button
                      onClick={() => handlePublishJudgment(j)}
                      disabled={pendingMutation === `publish:${j.id}`}
                      className="text-xs px-2.5 py-0.5 rounded font-medium focus-ring disabled:opacity-50"
                      style={{ background: 'var(--color-success)', color: 'var(--text-on-success, #fff)' }}
                      data-testid="publish-judgment-btn"
                    >
                      {pendingMutation === `publish:${j.id}` ? '发布中…' : '发布'}
                    </button>
                  )}
                </div>
                {/* T11: claim 是 Markdown, 自实现 renderInlineMarkdown 渲染 (**bold** / 列表 / 标题) */}
                <div
                  className="text-sm prose-sm"
                  style={{ color: 'var(--text-primary)' }}
                  dangerouslySetInnerHTML={{ __html: renderInlineMarkdown(j.claim) }}
                />
                {j.conditions && (
                  <div className="text-xs mt-2 italic" style={{ color: 'var(--text-muted)' }}>
                    适用条件: {j.conditions}
                  </div>
                )}
                {j.unknowns && j.unknowns.length > 0 && (
                  <div className="text-xs mt-1" style={{ color: 'var(--color-warning)' }}>
                    未知项: {j.unknowns.join('; ')}
                  </div>
                )}
                {j.evidence_refs && j.evidence_refs.length > 0 && (
                  <div className="text-xs mt-2" style={{ color: 'var(--text-muted)' }}>
                    证据 ({j.evidence_refs.length} 条): {j.evidence_refs.map(e => e.material_id).join(', ')}
                  </div>
                )}
              </div>
            ))}
          </div>
        )}
      </div>

      {/* 行动 + 运行 + 产物 */}
      <div id="section-actions" className="p-4 rounded-lg border" style={{ background: 'var(--bg-card)', borderColor: 'var(--line)' }}>
        <div className="flex flex-wrap items-center justify-between gap-2 mb-3">
          <h3 className="font-semibold" style={{ color: 'var(--text-primary)' }}>
            行动 (Action) + 运行 (Run) + 产物 (Artifact) {actionChainLoading && <span className="text-xs font-normal" style={{ color: 'var(--text-muted)' }}>加载中…</span>}
          </h3>
          {/* D2: SK-03 真实出稿 — 引用 published 判断 (§10.1) */}
          <button
            type="button"
            onClick={handleGenerateAction}
            disabled={generating !== null || !judgments.some(j => j.status === 'published')}
            title={judgments.some(j => j.status === 'published') ? 'SK-03 inspection-materials' : '需先生成并发布判断 (§10.1)'}
            className="text-xs px-3 py-1.5 rounded font-medium focus-ring disabled:opacity-50"
            style={{ background: 'var(--color-info)', color: 'var(--text-on-info, #fff)' }}
            data-testid="generate-action-btn"
          >
            {generating === 'action' ? '生成中…' : '生成行动 (SK-03)'}
          </button>
        </div>
        {actions.length === 0 ? (
          <div className="text-sm" style={{ color: 'var(--text-muted)' }}>暂无行动</div>
        ) : (
          <div className="space-y-4">
            {actions.map(a => {
              const actionRuns = runs.filter(r => r.action_id === a.id);
              const actionArtifacts = artifacts.filter(art => actionRuns.some(r => r.id === art.run_id));
              return (
                <div key={a.id} className="p-3 rounded border" style={{ borderColor: 'var(--line)' }}>
                  <div className="flex items-center gap-2 mb-2">
                    <span className="font-medium" style={{ color: 'var(--text-primary)' }}>{a.title}</span>
                    <Badge color={a.status === 'succeeded' ? 'green' : a.status === 'failed' ? 'red' : a.status === 'running' ? 'blue' : a.status === 'approved' ? 'yellow' : 'gray'}>{a.status}</Badge>
                    <span className="text-xs" style={{ color: 'var(--text-muted)' }}>rev {a.revision}</span>
                  </div>
                  <div className="text-xs font-mono mb-2" style={{ color: 'var(--text-muted)' }}>
                    {a.id} · plan_hash: {a.plan_hash?.slice(0, 12) ?? '-'}…
                    {a.expected_artifacts && a.expected_artifacts.length > 0 && (
                      <> · 预期产物: {a.expected_artifacts.join(', ')}</>
                    )}
                  </div>

                  {/* C10 R14/R15: 行动 mutation 按钮 (走 allowed_actions 守卫) */}
                  {Array.isArray((a as any).allowed_actions) && (a as any).allowed_actions.length > 0 && (
                    <div className="flex flex-wrap gap-2 mb-3">
                      {(a as any).allowed_actions.includes('approve') && (
                        <button
                          onClick={() => handleApproveAction(a)}
                          disabled={pendingMutation === `approve:${a.id}`}
                          className="text-xs px-3 py-1 rounded font-medium focus-ring disabled:opacity-50"
                          style={{ background: 'var(--color-info)', color: 'var(--text-on-info, #fff)' }}
                          data-testid="approve-action-btn"
                        >
                          {pendingMutation === `approve:${a.id}` ? '批准中…' : '批准'}
                        </button>
                      )}
                      {(a as any).allowed_actions.includes('start') && (
                        <button
                          onClick={() => handleStartAction(a)}
                          disabled={pendingMutation === `start:${a.id}`}
                          className="text-xs px-3 py-1 rounded font-medium focus-ring disabled:opacity-50"
                          style={{ background: 'var(--color-success)', color: 'var(--text-on-success, #fff)' }}
                          data-testid="start-action-btn"
                        >
                          {pendingMutation === `start:${a.id}` ? '启动中…' : '启动'}
                        </button>
                      )}
                      {(a as any).allowed_actions.includes('cancel') && (
                        <button
                          onClick={() => handleCancelAction(a)}
                          disabled={pendingMutation === `cancel:${a.id}`}
                          className="text-xs px-3 py-1 rounded font-medium focus-ring disabled:opacity-50"
                          style={{ background: 'var(--bg-muted)', color: 'var(--text-primary)', border: '1px solid var(--line)' }}
                          data-testid="cancel-action-btn"
                        >
                          {pendingMutation === `cancel:${a.id}` ? '取消中…' : '取消'}
                        </button>
                      )}
                    </div>
                  )}

                  {/* plan (T11 markdown 渲染) */}
                  {a.plan && (
                    <details className="mb-2">
                      <summary className="text-xs cursor-pointer" style={{ color: 'var(--text-muted)' }}>查看 plan</summary>
                      <div
                        className="text-xs mt-1 p-2 rounded prose-sm"
                        style={{ background: 'var(--bg-muted)', color: 'var(--text-primary)' }}
                        dangerouslySetInnerHTML={{ __html: renderInlineMarkdown(a.plan) }}
                      />
                    </details>
                  )}

                  {/* 运行 */}
                  {actionRuns.length > 0 && (
                    <div className="mb-3">
                      <div className="text-xs font-medium mb-1" style={{ color: 'var(--text-muted)' }}>运行 ({actionRuns.length} 次):</div>
                      {actionRuns.map(r => (
                        <div key={r.id} className="flex items-center gap-2 text-xs">
                          <Badge color={r.status === 'succeeded' ? 'green' : r.status === 'failed' ? 'red' : r.status === 'cancelled' ? 'gray' : 'blue'}>{r.status}</Badge>
                          <span className="font-mono" style={{ color: 'var(--text-muted)' }}>attempt #{r.attempt} · {r.protocol}</span>
                          <span style={{ color: 'var(--text-muted)' }}>{r.id}</span>
                          {r.error && <span style={{ color: 'var(--color-error)' }}>错误: {r.error.slice(0, 80)}</span>}
                        </div>
                      ))}
                    </div>
                  )}

                  {/* 产物 */}
                  {actionArtifacts.length > 0 ? (
                    <div>
                      <div className="text-xs font-medium mb-1" style={{ color: 'var(--text-muted)' }}>产物 ({actionArtifacts.length} 条):</div>
                      <div className="space-y-1">
                        {actionArtifacts.map(art => (
                          <div key={art.id} className="flex items-center gap-2 text-xs flex-wrap">
                            <span style={{ color: 'var(--text-primary)' }}>{art.title}</span>
                            <Badge color={art.status === 'accepted' ? 'green' : art.status === 'verified' ? 'blue' : art.status === 'rejected' ? 'red' : art.status === 'superseded' ? 'gray' : 'yellow'}>{art.status}</Badge>
                            <span style={{ color: 'var(--text-muted)' }}>{art.format} · {(art.size_bytes / 1024).toFixed(1)}KB</span>
                            {art.verified_result && <span style={{ color: 'var(--text-muted)' }}>· 验证: {art.verified_result}</span>}
                            {art.accepted_by && <span style={{ color: 'var(--text-success, var(--color-success))' }}>· 验收: {art.accepted_by}</span>}
                            {/* C10 R08/R14/R15: 产物 mutation 按钮 (accept 必先 verify — 走 allowed_actions 守卫) */}
                            {Array.isArray((art as any).allowed_actions) && (art as any).allowed_actions.length > 0 && (
                              <span className="flex gap-1.5 ml-auto">
                                {(art as any).allowed_actions.includes('verify') && (
                                  <button
                                    onClick={() => handleVerifyArtifact(art)}
                                    disabled={pendingMutation === `verify:${art.id}`}
                                    className="text-xs px-2 py-0.5 rounded font-medium focus-ring disabled:opacity-50"
                                    style={{ background: 'var(--color-info)', color: 'var(--text-on-info, #fff)' }}
                                    data-testid="verify-artifact-btn"
                                  >
                                    {pendingMutation === `verify:${art.id}` ? '验证中…' : '验证'}
                                  </button>
                                )}
                                {(art as any).allowed_actions.includes('accept') && (
                                  <button
                                    onClick={() => handleAcceptArtifact(art)}
                                    disabled={pendingMutation === `accept:${art.id}`}
                                    className="text-xs px-2 py-0.5 rounded font-medium focus-ring disabled:opacity-50"
                                    style={{ background: 'var(--color-success)', color: 'var(--text-on-success, #fff)' }}
                                    data-testid="accept-artifact-btn"
                                  >
                                    {pendingMutation === `accept:${art.id}` ? '验收中…' : '业务验收'}
                                  </button>
                                )}
                                {(art as any).allowed_actions.includes('reject') && (
                                  <button
                                    onClick={() => handleRejectArtifact(art)}
                                    disabled={pendingMutation === `reject:${art.id}`}
                                    className="text-xs px-2 py-0.5 rounded font-medium focus-ring disabled:opacity-50"
                                    style={{ background: 'var(--bg-muted)', color: 'var(--text-primary)', border: '1px solid var(--line)' }}
                                    data-testid="reject-artifact-btn"
                                  >
                                    {pendingMutation === `reject:${art.id}` ? '拒绝中…' : '拒绝'}
                                  </button>
                                )}
                              </span>
                            )}
                          </div>
                        ))}
                      </div>
                    </div>
                  ) : (
                    <div className="text-xs p-2 rounded" style={{ background: 'var(--bg-muted)', color: 'var(--text-muted)' }}>
                      缺资产: 此行动无产出产物 (baseline §5: 材料生成 ≠ 排查完成)
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}
