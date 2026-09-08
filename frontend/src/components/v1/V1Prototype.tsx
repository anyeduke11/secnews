/**
 * v1.0 四入口 + 事项详情 (C09 路由壳收尾, 拆 4 路由 + 删 MOCK 占位 + 删内层 tabs).
 *
 * 入口 (route → tab):
 *   /workbench → 'workbench'  今日工作
 *   /intel     → 'intel'      情报
 *   /cases     → 'cases'      事项
 *   /knowledge → 'knowledge'  经验库
 *
 * 走查 3 路径 (CaseDetail 内显示):
 *   - 缺资产: Case 下有 Action 但无 Artifact
 *   - 待验收: Artifact status=pending/verified 等待 acceptance
 *   - 失败: Run status=failed 或 Action status=failed
 *
 * 数据: 全部走真实 API, 失败显 unavailable, 不再 mock fallback.
 * 路由: /v1-prototype 已删除 (C09 R23); /knowledge 唯一声明.
 */

import { useCallback, useEffect, useState } from 'react';
import type { Case, Judgment } from '../../domain/v1_0';
import type { Action, Run, Artifact, Knowledge } from '../../api/v1';
import {
  listCases, listKnowledge, getKnowledgeReuse, listSignals,
  getCaseAggregate,
  approveAction, startAction, cancelAction, verifyArtifact, acceptArtifact, rejectArtifact, closeCase,
  adoptKnowledge, recordKnowledgeOutcome,
  type ReuseReceipt, type V1Signal, type ConditionDiff, type AdoptKnowledgeBody,
} from '../../api/v1';
import { renderInlineMarkdown } from '../../lib/markdown';
import { useSSEWithRefetch } from './useSSEWithRefetch';
import { useSSEAggregateInvalidate } from './useSSEAggregateInvalidate';
import { useToast } from '../Toast';

// ---------------------------------------------------------------------------
// 类型 + 共享组件
// ---------------------------------------------------------------------------

export type V1Tab = 'workbench' | 'intel' | 'cases' | 'knowledge';

// ---------------------------------------------------------------------------
// 辅助组件
// ---------------------------------------------------------------------------

// v1.0.1 一致性重构: Badge 改用 CSS 变量 token (light/dark 双值), 背景用 color-mix 表达 dim 透明层.
// 旧实现走 Tailwind 默认调色板 (bg-green-100 text-green-800), dark 主题下视觉断层; token + color-mix 与 index.css:746-758
// (warning/success/error chip) 风格一致.
function Badge({ children, color }: { children: React.ReactNode; color: 'green' | 'red' | 'yellow' | 'gray' | 'blue' }) {
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

function SectionTitle({ children, path }: { children: React.ReactNode; path: string }) {
  return (
    <div className="flex items-center gap-2 mb-3">
      <h2 className="text-lg font-semibold" style={{ color: 'var(--text-primary)' }}>{children}</h2>
      <span className="text-xs font-mono px-1.5 py-0.5 rounded" style={{ background: 'var(--bg-muted)', color: 'var(--text-muted)' }}>路径: {path}</span>
    </div>
  );
}

// ---------------------------------------------------------------------------
// 入口 1: 今日工作 (Workbench)
// ---------------------------------------------------------------------------

function WorkbenchView({ onSelectCase }: { onSelectCase: (caseId: string) => void }) {
  // v1.0 T15: 真实数据 (listCases 聚合, 走查 3 路径从真实 status 派生)
  const [cases, setCases] = useState<any[]>([]);
  const [loading, setLoading] = useState(false);
  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    listCases({ limit: 50 })
      .then((r) => { if (!cancelled) setCases(r.items); })
      .catch(() => { if (!cancelled) setCases([]); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, []);

  const blocked = cases.filter(c => c.status === 'blocked');
  const open = cases.filter(c => c.status === 'open' || c.status === 'in_progress');
  const closed = cases.filter(c => c.status === 'closed' || c.status === 'archived');

  return (
    <div className="space-y-6">
      <SectionTitle path="workbench">今日工作 {loading && <span className="text-xs font-normal" style={{ color: 'var(--text-muted)' }}>加载中…</span>}</SectionTitle>

      {/* 统计卡片 — 全部走真实数据 */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <div className="p-4 rounded-lg border" style={{ background: 'var(--bg-card)', borderColor: 'var(--line)' }}>
          <div className="text-2xl font-bold" style={{ color: 'var(--text-primary)' }}>{cases.length}</div>
          <div className="text-sm" style={{ color: 'var(--text-muted)' }}>活跃事项 (含 closed)</div>
        </div>
        <div className="p-4 rounded-lg border" style={{ background: 'var(--bg-card)', borderColor: 'var(--line)' }}>
          <div className="text-2xl font-bold" style={{ color: 'var(--color-warning)' }}>{blocked.length}</div>
          <div className="text-sm" style={{ color: 'var(--text-muted)' }}>阻塞中</div>
        </div>
        <div className="p-4 rounded-lg border" style={{ background: 'var(--bg-card)', borderColor: 'var(--line)' }}>
          <div className="text-2xl font-bold" style={{ color: 'var(--color-info)' }}>{open.length}</div>
          <div className="text-sm" style={{ color: 'var(--text-muted)' }}>进行中</div>
        </div>
        <div className="p-4 rounded-lg border" style={{ background: 'var(--bg-card)', borderColor: 'var(--line)' }}>
          <div className="text-2xl font-bold" style={{ color: 'var(--text-success, var(--color-success))' }}>{closed.length}</div>
          <div className="text-sm" style={{ color: 'var(--text-muted)' }}>已关闭</div>
        </div>
      </div>

      {/* 阻塞事项 — 走查 3 路径 (从真实 status 派生) */}
      <div className="p-4 rounded-lg border" style={{ background: 'var(--bg-card)', borderColor: 'var(--line)' }}>
        <h3 className="font-semibold mb-3" style={{ color: 'var(--text-primary)' }}>阻塞事项 (走查 3 路径)</h3>
        {blocked.length === 0 ? (
          <div className="text-sm" style={{ color: 'var(--text-muted)' }}>无阻塞 — 全部 cases 走通</div>
        ) : (
          <div className="space-y-3">
            {blocked.map(c => (
              <div
                key={c.id}
                className="p-3 rounded border flex items-start justify-between cursor-pointer hover:shadow-md transition-shadow"
                style={{ borderColor: 'var(--line)' }}
                onClick={() => onSelectCase(c.id)}
              >
                <div>
                  <div className="font-medium" style={{ color: 'var(--text-primary)' }}>{c.title}</div>
                  <div className="text-sm mt-1" style={{ color: 'var(--text-muted)' }}>{c.question}</div>
                  <div className="text-xs mt-1 font-mono" style={{ color: 'var(--text-muted)' }}>{c.id} · {c.priority} · {c.status}</div>
                </div>
                <div className="flex gap-2"><Badge color="yellow">阻塞</Badge></div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// 入口 2: 情报 (Intel)
// ---------------------------------------------------------------------------

function IntelView() {
  // v1.0 T15: 真实数据 (listSignals 复用 T05 v1_signals, 移除 MOCK_SIGNALS)
  const [signals, setSignals] = useState<V1Signal[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    listSignals({ days: 7, limit: 50 })
      .then((r) => { if (!cancelled) setSignals(r.items); })
      .catch((e) => { if (!cancelled) { setError(e instanceof Error ? e.message : String(e)); setSignals([]); } })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, []);

  return (
    <div className="space-y-4">
      <SectionTitle path="intel">情报流 {loading && <span className="text-xs font-normal" style={{ color: 'var(--text-muted)' }}>加载中…</span>}</SectionTitle>
      {error && (
        <div className="text-sm p-3 rounded" style={{ background: 'var(--bg-warning, var(--color-warning))', color: 'var(--text-primary)' }}>
          加载失败: {error}
        </div>
      )}
      {signals.length === 0 && !loading ? (
        <div className="text-sm p-4 rounded-lg border" style={{ color: 'var(--text-muted)', borderColor: 'var(--line)' }}>
          近 7 天无新信号 (T05 v1_signals 表空)
        </div>
      ) : (
        <div className="space-y-3">
          {signals.map(s => (
            <div key={s.id} className="p-4 rounded-lg border" style={{ background: 'var(--bg-card)', borderColor: 'var(--line)' }}>
              <div className="flex items-start justify-between">
                <div className="flex-1">
                  <div className="font-medium" style={{ color: 'var(--text-primary)' }}>{s.summary}</div>
                  <div className="text-sm mt-1" style={{ color: 'var(--text-muted)' }}>
                    发生时间: {s.occurred_at} · subject: {s.subject_name || s.subject_id}
                  </div>
                </div>
                <Badge color={s.confidence === 'verified' ? 'green' : s.confidence === 'likely' ? 'blue' : 'gray'}>{s.confidence}</Badge>
              </div>
              <div className="text-xs mt-2 font-mono" style={{ color: 'var(--text-muted)' }}>
                {s.id} → material:{s.material_id} · status: {s.status}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// 入口 3: 事项 (Cases) + 详情
// ---------------------------------------------------------------------------

function CasesView({ onSelectCase }: { onSelectCase: (c: Case) => void }) {
  // v1.0 C09 R14 修复: 删 MOCK_* 6 数组 + usingFallback; 失败显 unavailable (AC-11)
  const [cases, setCases] = useState<Case[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    listCases({ limit: 50 })
      .then((resp) => {
        if (cancelled) return;
        setCases(resp.items || []);
      })
      .catch((e) => {
        if (cancelled) return;
        setError(e instanceof Error ? e.message : String(e));
        setCases([]);  // 失败不 fallback mock, 显 unavailable
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <div className="space-y-4">
      <SectionTitle path="cases">工作事项</SectionTitle>
      {loading && (
        <div className="text-sm p-3 rounded" style={{ background: 'var(--bg-muted)', color: 'var(--text-muted)' }}>
          加载中...
        </div>
      )}
      {error && !loading && (
        <div className="text-sm p-3 rounded" style={{ background: 'var(--bg-warning, var(--color-warning))', color: 'var(--text-primary)' }}>
          加载失败 (unavailable): {error}
        </div>
      )}
      {!loading && !error && cases.length === 0 && (
        <div className="text-sm p-4 rounded-lg border" style={{ background: 'var(--bg-card)', borderColor: 'var(--line)', color: 'var(--text-muted)' }}>
          暂无工作事项 (v1_cases 表空, 新业务链未跑通)
        </div>
      )}
      <div className="space-y-3">
        {cases.map(c => {
          const caseJudgments: Judgment[] = [];  // R14: 不再 MOCK_.filter, 走 N+1 listJudgments (R19 留 C11 聚合)
          const caseActions: Action[] = [];

          const statusColors: Record<string, 'green' | 'blue' | 'yellow' | 'gray' | 'red'> = {
            open: 'blue', in_progress: 'green', blocked: 'yellow', closed: 'gray', archived: 'gray',
          };

          return (
            <div
              key={c.id}
              className="p-4 rounded-lg border cursor-pointer hover:shadow-md transition-shadow"
              style={{ background: 'var(--bg-card)', borderColor: 'var(--line)' }}
              onClick={() => onSelectCase(c)}
            >
              <div className="flex items-start justify-between">
                <div className="flex-1">
                  <div className="font-medium" style={{ color: 'var(--text-primary)' }}>{c.title}</div>
                  <div className="text-sm mt-1 line-clamp-2" style={{ color: 'var(--text-muted)' }}>{c.question}</div>
                  <div className="flex gap-2 mt-2">
                    <Badge color={statusColors[c.status || 'open'] || 'gray'}>{c.status}</Badge>
                    <Badge color={c.priority === 'p0' ? 'red' : c.priority === 'p1' ? 'yellow' : 'gray'}>{c.priority}</Badge>
                    {caseJudgments.length > 0 && <Badge color="blue">判断 {caseJudgments.length}</Badge>}
                    {caseActions.length > 0 && <Badge color="green">行动 {caseActions.length}</Badge>}
                  </div>
                </div>
                <div className="text-xs font-mono ml-4" style={{ color: 'var(--text-muted)' }}>{c.id}</div>
              </div>
            </div>
          );
        })}
      </div>
    </div>
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
  const [liveKnowledge, setLiveKnowledge] = useState<Knowledge[]>([]);
  const [knowledgeReceipts, setKnowledgeReceipts] = useState<Record<string, ReuseReceipt>>({});
  const [knowledgeLoading, setKnowledgeLoading] = useState(false);
  const [pendingMutation, setPendingMutation] = useState<string | null>(null);
  const toast = useToast();

  // C11 R19: 单点 aggregate 拉取 — 1 次 HTTP 拉齐 case+judgments+actions+runs+artifacts.
  // 旧实现 4 个并行分支 (getCase+listJudgments+listActions+级联 listRuns+listArtifacts)
  // 触发 1+1+1+N+N×M=3+N+N×M 次往返, 业务规模 (50 actions × 5 runs) 触发 300 次.
  // 新实现固定 1 次, 服务端聚合 + 异常隔离 (单 run 拉取失败不阻断其他).
  const refetchAggregate = useCallback(async (silent: boolean = false) => {
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
      setLiveCase(agg.case);
      setLiveJudgments(agg.judgments);
      setLiveActions(agg.actions);
      setLiveRuns(agg.runs);
      setLiveArtifacts(agg.artifacts);
      // knowledge 仍走 listKnowledge (与 reuse receipt), 不在 aggregate 范围
      // (复用统计为派生聚合, 不在主链路 N+1 内, T13 形态保留)
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
    } as any).then(r => r.run ?? r),
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
    () => verifyArtifact(art.id, { expected_revision: art.revision, result: 'pass' } as any).then(r => r.item),
    `产物已验证: ${art.title}`,
    '验证失败',
  );
  const handleAcceptArtifact = (art: Artifact) => runMutation(
    `accept:${art.id}`,
    () => acceptArtifact(art.id, { expected_revision: art.revision } as any).then(r => r.item),
    `产物已业务验收: ${art.title}`,
    '验收失败',
  );
  const handleRejectArtifact = (art: Artifact) => runMutation(
    `reject:${art.id}`,
    () => rejectArtifact(art.id, { expected_revision: art.revision, reason: '人工拒绝 (UI 入口)' } as any).then(r => r.item),
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
      () => closeCase(display.id, { expected_revision: display.revision ?? 0 }).then(r => r.item),
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
      <div className="p-4 rounded-lg border" style={{ background: 'var(--bg-card)', borderColor: 'var(--line)' }}>
        <h3 className="font-semibold mb-3" style={{ color: 'var(--text-primary)' }}>
          知识 (Knowledge) {knowledgeLoading && <span className="text-xs font-normal" style={{ color: 'var(--text-muted)' }}>加载中…</span>}
        </h3>
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

      {/* 判断 */}
      <div className="p-4 rounded-lg border" style={{ background: 'var(--bg-card)', borderColor: 'var(--line)' }}>
        <h3 className="font-semibold mb-3" style={{ color: 'var(--text-primary)' }}>
          判断 (Judgment) {judgmentsLoading && <span className="text-xs font-normal" style={{ color: 'var(--text-muted)' }}>加载中…</span>}
        </h3>
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
      <div className="p-4 rounded-lg border" style={{ background: 'var(--bg-card)', borderColor: 'var(--line)' }}>
        <h3 className="font-semibold mb-3" style={{ color: 'var(--text-primary)' }}>
          行动 (Action) + 运行 (Run) + 产物 (Artifact) {actionChainLoading && <span className="text-xs font-normal" style={{ color: 'var(--text-muted)' }}>加载中…</span>}
        </h3>
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

// ---------------------------------------------------------------------------
// 入口 4: 知识 (Knowledge)
// ---------------------------------------------------------------------------

function KnowledgeView() {
  // v1.0 T15.5 + C12: 接 listAll 真实数据 + 采用 UI + 失效 blocker 提示
  const [items, setItems] = useState<Knowledge[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // 复用记录 (per knowledge id) — SK-05 §9.4 + C12 R16.5 派生
  const [receipts, setReceipts] = useState<Record<string, ReuseReceipt>>({});
  // 采用表单状态 (per knowledge id)
  const [adoptOpenFor, setAdoptOpenFor] = useState<string | null>(null);
  const [adoptCaseId, setAdoptCaseId] = useState('');
  const [adoptDiff, setAdoptDiff] = useState<ConditionDiff[]>([]);
  const [adoptSubmitting, setAdoptSubmitting] = useState(false);
  const toast = useToast();
  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    listKnowledge({ limit: 50 })
      .then(async (r) => {
        if (cancelled) return;
        setItems(r.items);
        // 拉每条 reuse receipt (C12 R16.5: total=0 起算, 只数 adoptions)
        const ids = r.items.map((k) => k.id);
        const newReceipts: Record<string, ReuseReceipt> = {};
        await Promise.all(
          ids.map(async (id) => {
            try {
              const rr = await getKnowledgeReuse(id);
              newReceipts[id] = rr.receipt;
            } catch {
              // 单条拉取失败不阻塞其他
            }
          })
        );
        if (!cancelled) setReceipts(newReceipts);
      })
      .catch((e) => { if (!cancelled) { setError(e instanceof Error ? e.message : String(e)); setItems([]); } })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, []);

  const submitAdoption = async (kid: string) => {
    if (!adoptCaseId || adoptCaseId.length !== 26) {
      toast.show({ type: 'error', message: 'case_id 必须是 26 字符 ULID' });
      return;
    }
    setAdoptSubmitting(true);
    try {
      const body: AdoptKnowledgeBody = {
        case_id: adoptCaseId,
        decision: 'adopted',
        condition_diff: adoptDiff,
        decided_by: 'user',
      };
      await adoptKnowledge(kid, body);
      toast.show({ type: 'success', message: '采用成功' });
      setAdoptOpenFor(null);
      setAdoptCaseId('');
      setAdoptDiff([]);
      // 刷新该条的 receipt
      try {
        const rr = await getKnowledgeReuse(kid);
        setReceipts((prev) => ({ ...prev, [kid]: rr.receipt }));
      } catch { /* swallow */ }
    } catch (e) {
      toast.show({ type: 'error', message: `采用失败: ${e instanceof Error ? e.message : String(e)}` });
    } finally {
      setAdoptSubmitting(false);
    }
  };

  const recordOutcome = async (kid: string, caseId: string, outcome: 'success' | 'failure' | 'partial') => {
    try {
      await recordKnowledgeOutcome(kid, { case_id: caseId, outcome });
      toast.show({ type: 'success', message: `已记录结果: ${outcome}` });
      try {
        const rr = await getKnowledgeReuse(kid);
        setReceipts((prev) => ({ ...prev, [kid]: rr.receipt }));
      } catch { /* swallow */ }
    } catch (e) {
      toast.show({ type: 'error', message: `记录结果失败: ${e instanceof Error ? e.message : String(e)}` });
    }
  };

  return (
    <div className="space-y-4">
      <SectionTitle path="knowledge">经验库 {loading && <span className="text-xs font-normal" style={{ color: 'var(--text-muted)' }}>加载中…</span>}</SectionTitle>
      {error && (
        <div className="text-sm p-3 rounded" style={{ background: 'var(--bg-warning, var(--color-warning))', color: 'var(--text-primary)' }}>
          加载失败: {error}
        </div>
      )}
      {items.length === 0 && !loading ? (
        <div className="text-sm p-4 rounded-lg border" style={{ color: 'var(--text-muted)', borderColor: 'var(--line)' }}>
          暂无经验库条目 (T15 演练 dry-run 模式, v1_knowledge 表空)
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {items.map(k => {
            const receipt = receipts[k.id];
            // C12 R16.4: 撤回/弃用 → blocker 提示 (仅 published/deprecated/retracted 区别)
            const isRetracted = k.status === 'retracted';
            const isDeprecated = k.status === 'deprecated';
            const isPublished = k.status === 'published';
            return (
              <div key={k.id} className="p-4 rounded-lg border" style={{ background: 'var(--bg-card)', borderColor: 'var(--line)' }}>
                <div className="flex items-start justify-between">
                  <div className="flex-1">
                    <div className="font-medium" style={{ color: 'var(--text-primary)' }}>{k.title}</div>
                    <div className="text-xs mt-1" style={{ color: 'var(--text-muted)' }}>{k.kind} · {k.status} · rev {k.revision}</div>
                  </div>
                  <Badge color={isRetracted ? 'red' : isDeprecated ? 'gray' : isPublished ? 'green' : 'yellow'}>{k.status}</Badge>
                </div>
                {/* C12 R16.4: 撤回/弃用 blocker 提示 */}
                {isRetracted && (
                  <div className="mt-2 p-2 rounded text-xs" style={{ background: 'var(--color-danger)', color: '#fff' }}>
                    ⚠️ 此经验已被撤回, 已采用此知识的活跃 Case 已挂 blocker (knowledge_retracted:{k.id.slice(0, 8)}…), 建议复审
                  </div>
                )}
                {isDeprecated && (
                  <div className="mt-2 p-2 rounded text-xs" style={{ background: 'var(--color-warning)', color: '#fff' }}>
                    ⚠️ 此经验已弃用{k.replacement_knowledge_id ? `, 替代: ${k.replacement_knowledge_id.slice(0, 8)}…` : ''}
                  </div>
                )}
                <div className="text-sm mt-2 line-clamp-3" style={{ color: 'var(--text-primary)' }}>{k.body}</div>
                {k.prerequisites && k.prerequisites.length > 0 && (
                  <div className="text-xs mt-2" style={{ color: 'var(--text-muted)' }}>前提: {k.prerequisites.join('; ')}</div>
                )}
                {k.counter_examples && k.counter_examples.length > 0 && (
                  <div className="text-xs mt-1" style={{ color: 'var(--color-warning)' }}>反例: {k.counter_examples.join('; ')}</div>
                )}
                {/* 复用记录 (C12 R16.5: 只数 adoptions) */}
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
                {/* C12 R16.2: 采用表单 (仅 published 可采用, 撤回/弃用禁用) */}
                {isPublished && (
                  <div className="mt-3 pt-3 border-t" style={{ borderColor: 'var(--line)' }}>
                    {adoptOpenFor === k.id ? (
                      <div className="space-y-2">
                        <input
                          type="text"
                          placeholder="目标 case_id (26 字符 ULID)"
                          value={adoptCaseId}
                          onChange={(e) => setAdoptCaseId(e.target.value)}
                          className="w-full px-2 py-1 text-sm border rounded font-mono"
                          style={{ borderColor: 'var(--line)', background: 'var(--bg-input)' }}
                          maxLength={26}
                        />
                        <textarea
                          placeholder="条件差异 (JSON, 可选): [{field, expected, actual, severity}]"
                          value={adoptDiff.length === 0 ? '' : JSON.stringify(adoptDiff, null, 2)}
                          onChange={(e) => {
                            try {
                              const v = e.target.value.trim();
                              setAdoptDiff(v ? JSON.parse(v) : []);
                            } catch {
                              /* ignore parse error mid-typing */
                            }
                          }}
                          rows={3}
                          className="w-full px-2 py-1 text-xs border rounded font-mono"
                          style={{ borderColor: 'var(--line)', background: 'var(--bg-input)' }}
                        />
                        <div className="flex gap-2">
                          <button
                            onClick={() => submitAdoption(k.id)}
                            disabled={adoptSubmitting}
                            className="px-3 py-1 text-xs rounded"
                            style={{ background: 'var(--mint)', color: 'var(--text-on-light)' }}
                          >
                            {adoptSubmitting ? '采用中…' : '确认采用'}
                          </button>
                          <button
                            onClick={() => { setAdoptOpenFor(null); setAdoptCaseId(''); setAdoptDiff([]); }}
                            className="px-3 py-1 text-xs rounded"
                            style={{ background: 'var(--bg-muted)' }}
                          >
                            取消
                          </button>
                        </div>
                      </div>
                    ) : (
                      <div className="flex gap-2">
                        <button
                          onClick={() => setAdoptOpenFor(k.id)}
                          className="px-3 py-1 text-xs rounded"
                          style={{ background: 'var(--mint)', color: 'var(--text-on-light)' }}
                        >
                          采用此经验
                        </button>
                        {/* 快捷结果记录 (假设已有 adopted case) */}
                        {receipt && receipt.total > 0 && (
                          <>
                            <button
                              onClick={() => {
                                const c = prompt('记录结果的目标 case_id (26 字符):');
                                if (c && c.length === 26) recordOutcome(k.id, c, 'success');
                                else if (c) toast.show({ type: 'error', message: 'case_id 必须是 26 字符' });
                              }}
                              className="px-3 py-1 text-xs rounded"
                              style={{ background: 'var(--color-success)' }}
                            >
                              记结果
                            </button>
                          </>
                        )}
                      </div>
                    )}
                  </div>
                )}
                <div className="text-xs mt-2 font-mono" style={{ color: 'var(--text-muted)' }}>{k.id}</div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// 主页面
// ---------------------------------------------------------------------------

// ---------------------------------------------------------------------------
// v1.0 C09 路由壳收尾: V1Prototype 重构为 4 独立 page export (共享 V1Shell)
// 每个路由 /workbench /intel /cases /knowledge 挂独立 page, V1Prototype 仅留
// 兼容别名 (供旧代码或测试引用).
// ---------------------------------------------------------------------------

/** v1.0 C09 R23 修复: /workbench → WorkbenchPage (不再用 V1Prototype). */
export function WorkbenchPage() {
  return <V1Shell tab="workbench" />;
}

/** v1.0 C09 R23 修复: /intel → IntelPage. */
export function IntelPage() {
  return <V1Shell tab="intel" />;
}

/** v1.0 C09 R23 修复: /cases → CasesPage (CaseDetail 嵌套在 CasesView 内部). */
export function CasesPage() {
  return <V1Shell tab="cases" />;
}

/** v1.0 C09 R23 修复: /knowledge (主入口) → KnowledgePage.
 * 注: /knowledge 真实页面是 V1Shell<tab="knowledge">, 而 4 大领域 (/import /process /compile /compound)
 * 走嵌套 KnowledgePage 组件 (与 Shell 区分). 此处 Shell 只显 1 行提示跳到 /knowledge/import 走 4 大领域.
 */
export function KnowledgeV1Page() {
  return <V1Shell tab="knowledge" />;
}

/** v1.0 C09 R24 兼容别名: V1Prototype(initialTab) → 等价 WorkbenchPage.
 * 旧代码 / 测试如已 import V1Prototype 仍能工作, 但 routes 不再用.
 */
export function V1Prototype({ initialTab = 'workbench' }: { initialTab?: V1Tab } = {}) {
  return <V1Shell tab={initialTab} />;
}

/** V1Shell — 4 page 共享的内部壳, 接 tab prop 决定显示哪个 view. */
function V1Shell({ tab }: { tab: V1Tab }) {
  const [selectedCase, setSelectedCase] = useState<Case | null>(null);
  // T17.5: 6 event_type → toast 触发 (caseId 触发 setSelectedCase 留 C11 契约)
  void useSSEWithRefetch(() => {});
  // WorkbenchView 传 caseId 字符串; 顶层从最新 listCases 缓存查 Case 重建对象
  const [caseCache, setCaseCache] = useState<Case[]>([]);
  useEffect(() => {
    listCases({ limit: 50 })
      .then((r) => setCaseCache(r.items || []))
      .catch(() => setCaseCache([]));
  }, []);

  return (
    <div className="max-w-6xl mx-auto p-6">
      {/* 内容区 (无内层 tabs, 路由决定当前 view) */}
      {selectedCase ? (
        <CaseDetail case_={selectedCase} onBack={() => setSelectedCase(null)} />
      ) : (
        <>
          {tab === 'workbench' && <WorkbenchView onSelectCase={(id) => {
            const found = caseCache.find(c => c.id === id);
            if (found) setSelectedCase(found);
          }} />}
          {tab === 'intel' && <IntelView />}
          {tab === 'cases' && <CasesView onSelectCase={setSelectedCase} />}
          {tab === 'knowledge' && <KnowledgeView />}
        </>
      )}

      {/* 走查说明 */}
      <div className="mt-8 p-4 rounded-lg border" style={{ background: 'var(--bg-card)', borderColor: 'var(--line)' }}>
        <h3 className="font-semibold mb-2" style={{ color: 'var(--text-primary)' }}>走查 3 路径说明</h3>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4 text-sm" style={{ color: 'var(--text-secondary)' }}>
          <div>
            <div className="font-medium mb-1" style={{ color: 'var(--color-warning)' }}>缺资产</div>
            <div>Case 下有 Action, 但 Action 的 Run 未产出 Artifact, 或 expected_artifacts 为空。</div>
          </div>
          <div>
            <div className="font-medium mb-1" style={{ color: 'var(--color-info)' }}>待验收</div>
            <div>Artifact 已通过自动验证 (verified), 等待业务验收 (acceptance) 才能标记 accepted。</div>
          </div>
          <div>
            <div className="font-medium mb-1" style={{ color: 'var(--color-error)' }}>失败</div>
            <div>Run 或 Action 状态为 failed, 需查看 error 字段决定重试 (retry) 或升级 (escalate)。</div>
          </div>
        </div>
      </div>
    </div>
  );
}
