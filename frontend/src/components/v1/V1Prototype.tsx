/**
 * v1.0 四入口 + 事项详情原型 (T03-E).
 *
 * 入口:
 *   1. 今日工作 (Workbench) — 聚合看板
 *   2. 情报 (Intel) — Signal 流
 *   3. 事项 (Cases) — Case 列表 + 详情
 *   4. 知识 (Knowledge) — 经验库
 *
 * 走查 3 路径:
 *   - 缺资产: Case 下有 Action 但无 Artifact
 *   - 待验收: Artifact status=pending/verified 等待 acceptance
 *   - 失败: Run status=failed 或 Action status=failed
 *
 * 数据: 内嵌 mock (来自 dev_data/seed.json 脱敏样本), 明确标识为测试数据.
 * 路由: /v1-prototype (临时, T15 收口后移除)
 */

import { useEffect, useState } from 'react';
import type { Case, Judgment } from '../../domain/v1_0';
import type { Action, Run, Artifact, Knowledge } from '../../api/v1';
import { listCases, getCase, listJudgments, listActions, listRuns, listArtifacts, listKnowledge, getKnowledgeReuse, listSignals, type ReuseReceipt, type V1Signal } from '../../api/v1';
import { renderInlineMarkdown } from '../../lib/markdown';
import { useSSEWithRefetch } from './useSSEWithRefetch';

// ---------------------------------------------------------------------------
// Mock 数据 (来自 seed.json, 脱敏后内嵌避免 fetch 依赖)
// ---------------------------------------------------------------------------

type Tab = 'workbench' | 'intel' | 'cases' | 'knowledge';

const MOCK_CASES: Case[] = [
  { id: 'CASE001', title: '评估 CVE-2026-XXXX 对核心系统的影响', question: '该漏洞是否影响生产环境?', goal: '完成漏洞影响评估与修复建议', scope: '核心交易系统', priority: 'p0', status: 'in_progress', due_at: '2025-06-10T00:00:00+00:00', subject_id: 'SUBJ001', related_subject_ids: ['SUBJ002'], related_signal_ids: ['SIG001'], related_case_ids: [], tags: ['security', 'cve'], owner_role: 'user', revision: 1, closed_at: null, created_at: '2025-06-01T08:00:00+00:00', updated_at: '2025-06-04T09:00:00+00:00', allowed_actions: ['block', 'close', 'edit', 'add_judgment'], reason: null },
  { id: 'CASE002', title: '制定 AI 安全合规响应流程', question: '如何满足新规要求?', goal: '输出合规差距分析报告', scope: '全公司 AI 应用', priority: 'p1', status: 'open', due_at: '2025-06-15T00:00:00+00:00', subject_id: 'SUBJ002', related_subject_ids: [], related_signal_ids: ['SIG002'], related_case_ids: [], tags: ['ai_security', 'compliance'], owner_role: 'user', revision: 1, closed_at: null, created_at: '2025-06-02T10:30:00+00:00', updated_at: '2025-06-02T10:30:00+00:00', allowed_actions: ['claim', 'close', 'archive', 'edit'], reason: null },
  { id: 'CASE003', title: '供应链投毒事件复盘与防御', question: '如何防止类似事件?', goal: '形成可复用的检查清单', scope: '开源依赖', priority: 'p2', status: 'blocked', due_at: null, subject_id: 'SUBJ003', related_subject_ids: [], related_signal_ids: ['SIG003'], related_case_ids: [], tags: ['supply_chain'], owner_role: 'user', revision: 1, closed_at: null, created_at: '2025-06-03T14:00:00+00:00', updated_at: '2025-06-03T14:00:00+00:00', allowed_actions: ['unblock', 'edit', 'add_judgment'], reason: '等待安全团队提供漏洞详情' },
];

const MOCK_JUDGMENTS: Judgment[] = [
  { id: 'JUDG001', case_id: 'CASE001', subject_id: 'SUBJ001', claim_type: 'finding', claim: '该漏洞影响核心交易系统的支付模块, CVSS 评分 9.8, 需立即修复。', conditions: '适用于生产环境未打补丁的场景', confidence: 'high', evidence_refs: [{ material_id: 'MAT001', signal_id: 'SIG001', chunk_id: null, offset: null, hash: 'seed_abc123', quote: 'CVE-2026-XXXX 远程代码执行漏洞详情' }], counter_evidence_refs: [], unknowns: ['具体 affected versions 待确认'], status: 'published', revision: 1, wiki_path: null, content_hash: 'seed_judg001', published_at: '2025-06-04T09:00:00+00:00', created_at: '2025-06-04T09:00:00+00:00', updated_at: '2025-06-04T09:00:00+00:00', allowed_actions: ['create_supersede', 'retract', 'add_counter_evidence'] },
  { id: 'JUDG002', case_id: 'CASE002', subject_id: 'SUBJ002', claim_type: 'assessment', claim: '新规对现有流程影响中等, 需补充 3 个控制点。', conditions: '适用于金融科技场景', confidence: 'medium', evidence_refs: [{ material_id: 'MAT002', signal_id: 'SIG002', chunk_id: null, offset: null, hash: 'seed_def456', quote: '监管新规摘要' }], counter_evidence_refs: [], unknowns: ['具体罚款金额未公开'], status: 'draft', revision: 1, wiki_path: null, content_hash: null, published_at: null, created_at: '2025-06-03T16:00:00+00:00', updated_at: '2025-06-03T16:00:00+00:00', allowed_actions: ['edit', 'publish', 'discard'] },
];

const MOCK_ACTIONS: Action[] = [
  { id: 'ACT001', case_id: 'CASE001', judgment_id: 'JUDG001', title: '部署安全补丁', scope: '生产环境支付模块', plan: '# 部署计划\n\n1. 拉取补丁\n2. 灰度发布\n3. 验证修复\n\n验收: 漏洞扫描通过', plan_hash: 'seed_act001', tool_versions: {}, expected_artifacts: ['report'], success_criteria: 'CVSS 降至 3.0 以下', expires_at: null, status: 'running', approved_by: null, approved_at: null, revision: 1, created_at: '2025-06-04T10:00:00+00:00', updated_at: '2025-06-04T10:00:00+00:00', allowed_actions: ['cancel'] },
  { id: 'ACT002', case_id: 'CASE002', judgment_id: 'JUDG002', title: '合规差距分析', scope: '全公司 AI 应用', plan: '# 差距分析\n\n1. 梳理现有流程\n2. 对照新规\n3. 输出报告', plan_hash: 'seed_act002', tool_versions: {}, expected_artifacts: ['report'], success_criteria: '完成差距分析报告', expires_at: '2025-06-20T00:00:00+00:00', status: 'planned', approved_by: null, approved_at: null, revision: 1, created_at: '2025-06-03T16:30:00+00:00', updated_at: '2025-06-03T16:30:00+00:00', allowed_actions: ['approve', 'reject', 'edit', 'cancel'] },
];

const MOCK_RUNS: Run[] = [
  { id: 'run_000000000001', action_id: 'ACT001', attempt: 1, skill_id: 'patch-deploy', protocol: 'direct', trigger_source: 'user', idempotency_key: 'seed_run_000000000001', status: 'running', inputs: {}, steps: [], budget_tokens: null, budget_seconds: 3600, started_at: '2025-06-04T10:05:00+00:00', finished_at: null, duration_ms: null, result_excerpt: null, error: null, artifact_ids: [], revision: 1, created_at: '2025-06-04T10:05:00+00:00', updated_at: '2025-06-04T10:05:00+00:00', allowed_actions: [] },
  { id: 'run_000000000002', action_id: 'ACT002', attempt: 1, skill_id: 'gap-analysis', protocol: 'dsh', trigger_source: 'system', idempotency_key: 'seed_run_000000000002', status: 'queued', inputs: {}, steps: [], budget_tokens: null, budget_seconds: null, started_at: null, finished_at: null, duration_ms: null, result_excerpt: null, error: null, artifact_ids: [], revision: 1, created_at: '2025-06-04T11:00:00+00:00', updated_at: '2025-06-04T11:00:00+00:00', allowed_actions: [] },
  { id: 'run_000000000003', action_id: 'ACT001', attempt: 2, skill_id: 'patch-deploy', protocol: 'direct', trigger_source: 'user', idempotency_key: 'seed_run_000000000003', status: 'failed', inputs: {}, steps: [], budget_tokens: null, budget_seconds: null, started_at: '2025-06-03T14:00:00+00:00', finished_at: '2025-06-03T14:02:00+00:00', duration_ms: 120000, result_excerpt: null, error: '连接超时: 目标服务器无响应', artifact_ids: [], revision: 1, created_at: '2025-06-03T14:00:00+00:00', updated_at: '2025-06-03T14:02:00+00:00', allowed_actions: [] },
];

const MOCK_ARTIFACTS: Artifact[] = [
  { id: 'ART001', run_id: 'run_000000000001', kind: 'report', title: '漏洞修复验证报告', content_ref: null, content_hash: 'seed_art001', format: 'pdf', size_bytes: 102400, verified_by: null, verified_at: null, verified_result: null, accepted_by: null, accepted_at: null, accepted_note: null, status: 'pending', revision: 1, created_at: '2025-06-04T10:30:00+00:00', updated_at: '2025-06-04T10:30:00+00:00', allowed_actions: [] },
  { id: 'ART002', run_id: 'run_000000000001', kind: 'chart', title: '修复前后对比图', content_ref: null, content_hash: 'seed_art002', format: 'png', size_bytes: 51200, verified_by: 'ci-bot', verified_at: '2025-06-04T10:35:00+00:00', verified_result: 'pass', accepted_by: null, accepted_at: null, accepted_note: null, status: 'verified', revision: 1, created_at: '2025-06-04T10:30:00+00:00', updated_at: '2025-06-04T10:35:00+00:00', allowed_actions: ['accept'] },
  { id: 'ART003', run_id: 'run_000000000003', kind: 'report', title: '失败运行日志', content_ref: null, content_hash: 'seed_art003', format: 'txt', size_bytes: 2048, verified_by: null, verified_at: null, verified_result: null, accepted_by: null, accepted_at: null, accepted_note: null, status: 'rejected', revision: 1, created_at: '2025-06-03T14:02:00+00:00', updated_at: '2025-06-03T14:02:00+00:00', allowed_actions: [] },
];

const MOCK_KNOWLEDGE: Knowledge[] = [
  { id: 'KNOW001', kind: 'playbook', title: '漏洞响应标准流程', body: '# 漏洞响应\n\n1. 确认影响范围\n2. 评估风险\n3. 制定修复计划\n4. 执行与验证', prerequisites: ['具备漏洞扫描权限'], counter_examples: [], evidence_refs: [], expiry_at: null, review_at: '2025-12-01T00:00:00+00:00', status: 'published', revision: 1, wiki_path: null, content_hash: 'seed_know001', published_at: '2025-01-01T00:00:00+00:00', created_at: '2025-01-01T00:00:00+00:00', updated_at: '2025-05-15T00:00:00+00:00', allowed_actions: ['create_revision', 'deprecate', 'retract'] },
  { id: 'KNOW002', kind: 'anti_pattern', title: '补丁部署常见错误', body: '# 反例\n\n- 未在 staging 验证直接部署生产\n- 忽略回滚计划', prerequisites: [], counter_examples: ['某次未验证导致服务中断 2 小时'], evidence_refs: [], expiry_at: null, review_at: null, status: 'draft', revision: 1, wiki_path: null, content_hash: null, published_at: null, created_at: '2025-06-01T00:00:00+00:00', updated_at: '2025-06-01T00:00:00+00:00', allowed_actions: ['edit', 'publish', 'discard'] },
];

// ---------------------------------------------------------------------------
// 辅助组件
// ---------------------------------------------------------------------------

function Badge({ children, color }: { children: React.ReactNode; color: 'green' | 'red' | 'yellow' | 'gray' | 'blue' }) {
  const colors: Record<string, string> = {
    green: 'bg-green-100 text-green-800',
    red: 'bg-red-100 text-red-800',
    yellow: 'bg-yellow-100 text-yellow-800',
    gray: 'bg-gray-100 text-gray-800',
    blue: 'bg-blue-100 text-blue-800',
  };
  return <span className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-medium ${colors[color] || colors.gray}`}>{children}</span>;
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
        <div className="p-4 rounded-lg border" style={{ background: 'var(--bg-card)', borderColor: 'var(--border-muted)' }}>
          <div className="text-2xl font-bold" style={{ color: 'var(--text-primary)' }}>{cases.length}</div>
          <div className="text-sm" style={{ color: 'var(--text-muted)' }}>活跃事项 (含 closed)</div>
        </div>
        <div className="p-4 rounded-lg border" style={{ background: 'var(--bg-card)', borderColor: 'var(--border-muted)' }}>
          <div className="text-2xl font-bold" style={{ color: 'var(--color-warning)' }}>{blocked.length}</div>
          <div className="text-sm" style={{ color: 'var(--text-muted)' }}>阻塞中</div>
        </div>
        <div className="p-4 rounded-lg border" style={{ background: 'var(--bg-card)', borderColor: 'var(--border-muted)' }}>
          <div className="text-2xl font-bold" style={{ color: 'var(--color-info)' }}>{open.length}</div>
          <div className="text-sm" style={{ color: 'var(--text-muted)' }}>进行中</div>
        </div>
        <div className="p-4 rounded-lg border" style={{ background: 'var(--bg-card)', borderColor: 'var(--border-muted)' }}>
          <div className="text-2xl font-bold" style={{ color: 'var(--text-success, var(--color-success))' }}>{closed.length}</div>
          <div className="text-sm" style={{ color: 'var(--text-muted)' }}>已关闭</div>
        </div>
      </div>

      {/* 阻塞事项 — 走查 3 路径 (从真实 status 派生) */}
      <div className="p-4 rounded-lg border" style={{ background: 'var(--bg-card)', borderColor: 'var(--border-muted)' }}>
        <h3 className="font-semibold mb-3" style={{ color: 'var(--text-primary)' }}>阻塞事项 (走查 3 路径)</h3>
        {blocked.length === 0 ? (
          <div className="text-sm" style={{ color: 'var(--text-muted)' }}>无阻塞 — 全部 cases 走通</div>
        ) : (
          <div className="space-y-3">
            {blocked.map(c => (
              <div
                key={c.id}
                className="p-3 rounded border flex items-start justify-between cursor-pointer hover:shadow-md transition-shadow"
                style={{ borderColor: 'var(--border-muted)' }}
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
        <div className="text-sm p-4 rounded-lg border" style={{ color: 'var(--text-muted)', borderColor: 'var(--border-muted)' }}>
          近 7 天无新信号 (T05 v1_signals 表空)
        </div>
      ) : (
        <div className="space-y-3">
          {signals.map(s => (
            <div key={s.id} className="p-4 rounded-lg border" style={{ background: 'var(--bg-card)', borderColor: 'var(--border-muted)' }}>
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
  const [cases, setCases] = useState<Case[]>(MOCK_CASES);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [usingFallback, setUsingFallback] = useState(true);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    listCases({ limit: 50 })
      .then((resp) => {
        if (cancelled) return;
        if (resp.items && resp.items.length > 0) {
          setCases(resp.items);
          setUsingFallback(false);
        } else {
          // 后端空 → 用 mock 演示
          setUsingFallback(true);
        }
      })
      .catch((e) => {
        if (cancelled) return;
        // API 失败 → 保留 mock (设计要求 fallback)
        setError(e instanceof Error ? e.message : String(e));
        setUsingFallback(true);
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
        <div className="text-sm p-3 rounded" style={{ background: 'var(--bg-warning)', color: 'var(--color-warning)' }}>
          API 调用失败, 显示本地示例数据: {error}
        </div>
      )}
      {!loading && !error && usingFallback && cases.length === MOCK_CASES.length && (
        <div className="text-sm p-3 rounded" style={{ background: 'var(--bg-muted)', color: 'var(--text-muted)' }}>
          当前无后端数据, 显示本地示例 (mock fallback)。
        </div>
      )}
      <div className="space-y-3">
        {cases.map(c => {
          const caseJudgments = MOCK_JUDGMENTS.filter(j => j.case_id === c.id);
          const caseActions = MOCK_ACTIONS.filter(a => a.case_id === c.id);

          const statusColors: Record<string, 'green' | 'blue' | 'yellow' | 'gray' | 'red'> = {
            open: 'blue', in_progress: 'green', blocked: 'yellow', closed: 'gray', archived: 'gray',
          };

          return (
            <div
              key={c.id}
              className="p-4 rounded-lg border cursor-pointer hover:shadow-md transition-shadow"
              style={{ background: 'var(--bg-card)', borderColor: 'var(--border-muted)' }}
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

function CaseDetail({ case_, onBack }: { case_: Case; onBack: () => void }) {
  const [liveCase, setLiveCase] = useState<Case | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [usingFallback, setUsingFallback] = useState(true);
  const [liveJudgments, setLiveJudgments] = useState<Judgment[]>([]);
  const [judgmentsLoading, setJudgmentsLoading] = useState(false);
  const [liveActions, setLiveActions] = useState<Action[]>([]);
  const [liveRuns, setLiveRuns] = useState<Run[]>([]);
  const [liveArtifacts, setLiveArtifacts] = useState<Artifact[]>([]);
  const [actionChainLoading, setActionChainLoading] = useState(false);
  const [liveKnowledge, setLiveKnowledge] = useState<Knowledge[]>([]);
  const [knowledgeReceipts, setKnowledgeReceipts] = useState<Record<string, ReuseReceipt>>({});
  const [knowledgeLoading, setKnowledgeLoading] = useState(false);

  // T08 + T11 + T12 + T13: 真实数据接入 — case / judgment / action / run / artifact / knowledge
  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    getCase(case_.id)
      .then((resp) => { if (!cancelled) { setLiveCase(resp.item); setUsingFallback(false); } })
      .catch((e) => { if (!cancelled) { setError(e instanceof Error ? e.message : String(e)); setLiveCase(null); setUsingFallback(true); } })
      .finally(() => { if (!cancelled) setLoading(false); });
    setJudgmentsLoading(true);
    listJudgments({ case_id: case_.id, limit: 50 })
      .then((resp) => { if (!cancelled) setLiveJudgments(resp.items); })
      .catch(() => { if (!cancelled) setLiveJudgments([]); })
      .finally(() => { if (!cancelled) setJudgmentsLoading(false); });
    // T12: 拉 actions (含级联 runs + artifacts)
    setActionChainLoading(true);
    listActions({ case_id: case_.id, limit: 50 })
      .then(async (resp) => {
        if (cancelled) return;
        setLiveActions(resp.items);
        const allRuns: Run[] = [];
        const allArts: Artifact[] = [];
        for (const a of resp.items) {
          try {
            const r = await listRuns({ action_id: a.id, limit: 10 });
            allRuns.push(...r.items);
            for (const run of r.items) {
              try {
                const arts = await listArtifacts({ run_id: run.id, limit: 10 });
                allArts.push(...arts.items);
              } catch { /* 静默 */ }
            }
          } catch { /* 静默 */ }
        }
        if (!cancelled) {
          setLiveRuns(allRuns);
          setLiveArtifacts(allArts);
        }
      })
      .catch(() => { if (!cancelled) { setLiveActions([]); setLiveRuns([]); setLiveArtifacts([]); } })
      .finally(() => { if (!cancelled) setActionChainLoading(false); });
    // T13: 拉 knowledge 列表 (含 reuse receipt)
    setKnowledgeLoading(true);
    listKnowledge({ case_id: case_.id, limit: 50 })
      .then(async (resp) => {
        if (cancelled) return;
        setLiveKnowledge(resp.items);
        // 拉每个 knowledge 的 reuse receipt
        const receipts: Record<string, ReuseReceipt> = {};
        for (const k of resp.items) {
          try {
            const r = await getKnowledgeReuse(k.id);
            receipts[k.id] = r.receipt;
          } catch { /* 静默 */ }
        }
        if (!cancelled) setKnowledgeReceipts(receipts);
      })
      .catch(() => { if (!cancelled) { setLiveKnowledge([]); setKnowledgeReceipts({}); } })
      .finally(() => { if (!cancelled) setKnowledgeLoading(false); });
    return () => { cancelled = true; };
  }, [case_.id]);

  const display = liveCase ?? case_;
  // T11: 优先真实 judgment, 失败回退 mock
  const judgments = liveJudgments.length > 0
    ? liveJudgments
    : MOCK_JUDGMENTS.filter(j => j.case_id === display.id);
  // T12: 优先真实 action/run/artifact, 失败回退 mock
  const usingLiveActionChain = liveActions.length > 0;
  const actions = usingLiveActionChain
    ? liveActions
    : MOCK_ACTIONS.filter(a => a.case_id === display.id);
  const actionIds = actions.map(a => a.id);
  const runs = usingLiveActionChain
    ? liveRuns
    : MOCK_RUNS.filter(r => actionIds.includes(r.action_id));
  const runIds = runs.map(r => r.id);
  const artifacts = usingLiveActionChain
    ? liveArtifacts
    : MOCK_ARTIFACTS.filter(a => runIds.includes(a.run_id));

  // 走查 3 路径检测 (T12 强化: 显式呈现 3 路径而非简单色块)
  const hasMissingAssets = actions.length > 0 && artifacts.length === 0;
  const hasFailure = runs.some(r => r.status === 'failed');
  const hasPendingAcceptance = artifacts.some(a => a.status === 'verified');
  const hasRejected = artifacts.some(a => a.status === 'rejected');
  // T13: 优先真实 knowledge, 失败回退 mock
  const usingLiveKnowledge = liveKnowledge.length > 0;
  const knowledgeItems = usingLiveKnowledge
    ? liveKnowledge
    : MOCK_KNOWLEDGE.filter(k => k.evidence_refs?.some(r => {
        const j = liveJudgments.find(j => j.evidence_refs?.some(e => e.material_id === r.material_id));
        return !!j;
      }));

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
        <div className="flex gap-2">
          <Badge color={display.status === 'open' ? 'blue' : display.status === 'in_progress' ? 'green' : display.status === 'blocked' ? 'yellow' : 'gray'}>{display.status}</Badge>
          <Badge color={display.priority === 'p0' ? 'red' : display.priority === 'p1' ? 'yellow' : 'gray'}>{display.priority}</Badge>
        </div>
      </div>

      {/* T08 加载 / 错误 / fallback 提示 */}
      {loading && (
        <div className="p-3 rounded-lg border text-sm" style={{ background: 'var(--bg-muted)', borderColor: 'var(--border-muted)', color: 'var(--text-muted)' }}>
          加载中...
        </div>
      )}
      {error && !loading && (
        <div className="p-3 rounded-lg border text-sm" style={{ background: 'var(--bg-warning)', borderColor: 'var(--color-warning)', color: 'var(--color-warning)' }}>
          API 调用失败, 显示列表缓存数据: {error}
        </div>
      )}
      {!loading && !error && !usingFallback && (
        <div className="p-3 rounded-lg border text-sm" style={{ background: 'var(--bg-card)', borderColor: 'var(--border-muted)', color: 'var(--text-muted)' }}>
          已加载后端数据 · revision {display.revision} · allowed_actions: {display.allowed_actions?.join(', ') || '(none)'}
        </div>
      )}

      {/* 走查 3 路径指示器 (T12 强化: 显式呈现) */}
      <div className="p-3 rounded-lg border" style={{ background: 'var(--bg-muted)', borderColor: 'var(--border-muted)' }}>
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
      <div className="p-4 rounded-lg border" style={{ background: 'var(--bg-card)', borderColor: 'var(--border-muted)' }}>
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
                <div key={k.id} className="p-3 rounded border" style={{ borderColor: 'var(--border-muted)' }}>
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
                  {/* 复用记录 (SK-05 §9.4 派生) */}
                  {receipt && (
                    <div className="text-xs mt-2 p-2 rounded" style={{ background: 'var(--bg-muted)', color: 'var(--text-muted)' }}>
                      复用: total={receipt.total} (judgment {receipt.by_judgment} + action {receipt.by_action}) · 近 30 天 {receipt.recent_30d}
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
      <div className="p-4 rounded-lg border" style={{ background: 'var(--bg-card)', borderColor: 'var(--border-muted)' }}>
        <h3 className="font-semibold mb-3" style={{ color: 'var(--text-primary)' }}>
          判断 (Judgment) {judgmentsLoading && <span className="text-xs font-normal" style={{ color: 'var(--text-muted)' }}>加载中…</span>}
        </h3>
        {judgments.length === 0 ? (
          <div className="text-sm" style={{ color: 'var(--text-muted)' }}>暂无判断</div>
        ) : (
          <div className="space-y-3">
            {judgments.map(j => (
              <div key={j.id} className="p-3 rounded border" style={{ borderColor: 'var(--border-muted)' }}>
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
      <div className="p-4 rounded-lg border" style={{ background: 'var(--bg-card)', borderColor: 'var(--border-muted)' }}>
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
                <div key={a.id} className="p-3 rounded border" style={{ borderColor: 'var(--border-muted)' }}>
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
                          <div key={art.id} className="flex items-center gap-2 text-xs">
                            <span style={{ color: 'var(--text-primary)' }}>{art.title}</span>
                            <Badge color={art.status === 'accepted' ? 'green' : art.status === 'verified' ? 'blue' : art.status === 'rejected' ? 'red' : art.status === 'superseded' ? 'gray' : 'yellow'}>{art.status}</Badge>
                            <span style={{ color: 'var(--text-muted)' }}>{art.format} · {(art.size_bytes / 1024).toFixed(1)}KB</span>
                            {art.verified_result && <span style={{ color: 'var(--text-muted)' }}>· 验证: {art.verified_result}</span>}
                            {art.accepted_by && <span style={{ color: 'var(--text-success, var(--color-success))' }}>· 验收: {art.accepted_by}</span>}
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
  // v1.0 T15.5: 接 listAll 真实数据 (无 case_id 走全局)
  const [items, setItems] = useState<any[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    listKnowledge({ limit: 50 })
      .then((r) => { if (!cancelled) setItems(r.items); })
      .catch((e) => { if (!cancelled) { setError(e instanceof Error ? e.message : String(e)); setItems([]); } })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, []);
  return (
    <div className="space-y-4">
      <SectionTitle path="knowledge">经验库 {loading && <span className="text-xs font-normal" style={{ color: 'var(--text-muted)' }}>加载中…</span>}</SectionTitle>
      {error && (
        <div className="text-sm p-3 rounded" style={{ background: 'var(--bg-warning, var(--color-warning))', color: 'var(--text-primary)' }}>
          加载失败: {error}
        </div>
      )}
      {items.length === 0 && !loading ? (
        <div className="text-sm p-4 rounded-lg border" style={{ color: 'var(--text-muted)', borderColor: 'var(--border-muted)' }}>
          暂无经验库条目 (T15 演练 dry-run 模式, v1_knowledge 表空)
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {items.map(k => (
            <div key={k.id} className="p-4 rounded-lg border" style={{ background: 'var(--bg-card)', borderColor: 'var(--border-muted)' }}>
              <div className="flex items-start justify-between">
                <div className="flex-1">
                  <div className="font-medium" style={{ color: 'var(--text-primary)' }}>{k.title}</div>
                  <div className="text-xs mt-1" style={{ color: 'var(--text-muted)' }}>{k.kind} · {k.status}</div>
                </div>
                <Badge color={k.status === 'published' ? 'green' : k.status === 'draft' ? 'yellow' : 'gray'}>{k.status}</Badge>
              </div>
              <div className="text-sm mt-2 line-clamp-3" style={{ color: 'var(--text-primary)' }}>{k.body}</div>
              <div className="text-xs mt-2 font-mono" style={{ color: 'var(--text-muted)' }}>{k.id}</div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// 主页面
// ---------------------------------------------------------------------------

export function V1Prototype() {
  const [tab, setTab] = useState<Tab>('workbench');
  const [selectedCase, setSelectedCase] = useState<Case | null>(null);
  // T17.5: 6 event_type → toast 触发 + 4 view refetch
  useSSEWithRefetch(setTab);  // T19: 增 (caseId) => setSelectedCase(...) 占位

  const tabs: { key: Tab; label: string; icon: string }[] = [
    { key: 'workbench', label: '今日工作', icon: '📊' },
    { key: 'intel', label: '情报', icon: '📡' },
    { key: 'cases', label: '事项', icon: '📋' },
    { key: 'knowledge', label: '知识', icon: '📚' },
  ];

  return (
    <div className="max-w-6xl mx-auto p-6">
      {/* 测试数据标识 */}
      <div className="mb-6 p-3 rounded-lg border flex items-center gap-2" style={{ background: 'var(--bg-warning)', borderColor: 'var(--color-warning)' }}>
        <span className="text-sm font-medium" style={{ color: 'var(--color-warning)' }}>⚠️ 原型模式</span>
        <span className="text-sm" style={{ color: 'var(--text-primary)' }}>以下数据为 T03-E 脱敏测试样本, 来自 dev_data/seed.json, 不反映生产状态。</span>
      </div>

      {/* 标签栏 */}
      <div className="flex gap-1 p-1 rounded-lg mb-6" style={{ background: 'var(--bg-muted)' }}>
        {tabs.map(t => (
          <button
            key={t.key}
            onClick={() => { setTab(t.key); setSelectedCase(null); }}
            className={`px-4 py-2 rounded-md text-sm font-medium transition-colors ${tab === t.key ? 'shadow-sm' : ''}`}
            style={{
              background: tab === t.key ? 'var(--bg-card)' : 'transparent',
              color: tab === t.key ? 'var(--text-primary)' : 'var(--text-muted)',
            }}
          >
            <span className="mr-1">{t.icon}</span>
            {t.label}
          </button>
        ))}
      </div>

      {/* 内容区 */}
      {selectedCase ? (
        <CaseDetail case_={selectedCase} onBack={() => setSelectedCase(null)} />
      ) : (
        <>
          {tab === 'workbench' && <WorkbenchView onSelectCase={(id) => {
            setSelectedCase({ id, title: '...', question: '...', revision: 1, status: 'open', created_at: '2026-09-01T00:00:00+00:00', updated_at: '2026-09-01T00:00:00+00:00' } as Case);
            setTab('cases');
          }} />}
          {tab === 'intel' && <IntelView />}
          {tab === 'cases' && <CasesView onSelectCase={setSelectedCase} />}
          {tab === 'knowledge' && <KnowledgeView />}
        </>
      )}

      {/* 走查说明 */}
      <div className="mt-8 p-4 rounded-lg border" style={{ background: 'var(--bg-card)', borderColor: 'var(--border-muted)' }}>
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
