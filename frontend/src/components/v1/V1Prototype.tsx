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
import type { Case, Judgment, Action, Run, Artifact, Knowledge, Signal } from '../../domain/v1_0';
import { listCases, getCase } from '../../api/v1';

// ---------------------------------------------------------------------------
// Mock 数据 (来自 seed.json, 脱敏后内嵌避免 fetch 依赖)
// ---------------------------------------------------------------------------

type Tab = 'workbench' | 'intel' | 'cases' | 'knowledge';

const MOCK_SIGNALS: Signal[] = [
  { id: 'SIG001', subject_id: 'SUBJ001', material_id: 'MAT001', summary: '检测到 CVE-2026-XXXX 高危漏洞', occurred_at: '2025-06-01T08:00:00+00:00', admission_rule_version: 'v1.0_seed', admission_reason: '高影响安全事件', supersedes_signal_id: null, confidence: 'verified', revision: 1, status: 'verified', created_at: '2025-06-01T08:00:00+00:00', updated_at: '2025-06-01T08:00:00+00:00', allowed_actions: ['retract'] },
  { id: 'SIG002', subject_id: 'SUBJ002', material_id: 'MAT002', summary: '某金融科技公司发布 AI 安全新规', occurred_at: '2025-06-02T10:30:00+00:00', admission_rule_version: 'v1.0_seed', admission_reason: '监管动态', supersedes_signal_id: null, confidence: 'likely', revision: 1, status: 'likely', created_at: '2025-06-02T10:30:00+00:00', updated_at: '2025-06-02T10:30:00+00:00', allowed_actions: ['promote_verified', 'demote_unverified', 'retract'] },
  { id: 'SIG003', subject_id: 'SUBJ003', material_id: 'MAT003', summary: '开源供应链出现恶意投毒案例', occurred_at: '2025-06-03T14:00:00+00:00', admission_rule_version: 'v1.0_seed', admission_reason: '供应链安全', supersedes_signal_id: null, confidence: 'unverified', revision: 1, status: 'unverified', created_at: '2025-06-03T14:00:00+00:00', updated_at: '2025-06-03T14:00:00+00:00', allowed_actions: ['promote_likely', 'retract', 'edit_summary'] },
];

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
  { id: 'KNOW001', kind: 'playbook', title: '漏洞响应标准流程', body: '# 漏洞响应\n\n1. 确认影响范围\n2. 评估风险\n3. 制定修复计划\n4. 执行与验证', prerequisites: ['具备漏洞扫描权限'], counter_examples: [], evidence_refs: [], expiry_at: null, review_at: '2025-12-01T00:00:00+00:00', reuse_count: 3, last_reused_at: '2025-05-15T00:00:00+00:00', status: 'published', revision: 1, wiki_path: null, content_hash: 'seed_know001', published_at: '2025-01-01T00:00:00+00:00', created_at: '2025-01-01T00:00:00+00:00', updated_at: '2025-05-15T00:00:00+00:00', allowed_actions: ['create_revision', 'deprecate', 'retract'] },
  { id: 'KNOW002', kind: 'anti_pattern', title: '补丁部署常见错误', body: '# 反例\n\n- 未在 staging 验证直接部署生产\n- 忽略回滚计划', prerequisites: [], counter_examples: ['某次未验证导致服务中断 2 小时'], evidence_refs: [], expiry_at: null, review_at: null, reuse_count: 0, last_reused_at: null, status: 'draft', revision: 1, wiki_path: null, content_hash: null, published_at: null, created_at: '2025-06-01T00:00:00+00:00', updated_at: '2025-06-01T00:00:00+00:00', allowed_actions: ['edit', 'publish', 'discard'] },
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

function WorkbenchView() {
  const blockedCases = MOCK_CASES.filter(c => c.status === 'blocked');
  const failedRuns = MOCK_RUNS.filter(r => r.status === 'failed');
  const pendingArtifacts = MOCK_ARTIFACTS.filter(a => a.status === 'verified');

  return (
    <div className="space-y-6">
      <SectionTitle path="workbench">今日工作</SectionTitle>

      {/* 统计卡片 */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <div className="p-4 rounded-lg border" style={{ background: 'var(--bg-card)', borderColor: 'var(--border-muted)' }}>
          <div className="text-2xl font-bold" style={{ color: 'var(--text-primary)' }}>{MOCK_CASES.length}</div>
          <div className="text-sm" style={{ color: 'var(--text-muted)' }}>活跃事项</div>
        </div>
        <div className="p-4 rounded-lg border" style={{ background: 'var(--bg-card)', borderColor: 'var(--border-muted)' }}>
          <div className="text-2xl font-bold" style={{ color: 'var(--color-warning)' }}>{blockedCases.length}</div>
          <div className="text-sm" style={{ color: 'var(--text-muted)' }}>阻塞中</div>
        </div>
        <div className="p-4 rounded-lg border" style={{ background: 'var(--bg-card)', borderColor: 'var(--border-muted)' }}>
          <div className="text-2xl font-bold" style={{ color: 'var(--color-error)' }}>{failedRuns.length}</div>
          <div className="text-sm" style={{ color: 'var(--text-muted)' }}>失败运行</div>
        </div>
        <div className="p-4 rounded-lg border" style={{ background: 'var(--bg-card)', borderColor: 'var(--border-muted)' }}>
          <div className="text-2xl font-bold" style={{ color: 'var(--color-success)' }}>{pendingArtifacts.length}</div>
          <div className="text-sm" style={{ color: 'var(--text-muted)' }}>待验收产物</div>
        </div>
      </div>

      {/* 阻塞事项 — 走查路径: 缺资产 */}
      <div className="p-4 rounded-lg border" style={{ background: 'var(--bg-card)', borderColor: 'var(--border-muted)' }}>
        <h3 className="font-semibold mb-3" style={{ color: 'var(--text-primary)' }}>阻塞事项 (缺资产 / 待验收 / 失败)</h3>
        <div className="space-y-3">
          {blockedCases.map(c => {
            const caseActions = MOCK_ACTIONS.filter(a => a.case_id === c.id);
            const caseRuns = MOCK_RUNS.filter(r => r.action_id === caseActions[0]?.id);
            const caseArtifacts = MOCK_ARTIFACTS.filter(a => a.run_id === caseRuns[0]?.id);
            const hasMissingAssets = caseActions.length > 0 && caseArtifacts.length === 0;
            const hasFailure = caseRuns.some(r => r.status === 'failed');
            const hasPendingAcceptance = caseArtifacts.some(a => a.status === 'verified');

            let pathTag = null;
            if (hasMissingAssets) pathTag = <Badge color="yellow">缺资产</Badge>;
            if (hasFailure) pathTag = <Badge color="red">失败</Badge>;
            if (hasPendingAcceptance) pathTag = <Badge color="blue">待验收</Badge>;

            return (
              <div key={c.id} className="p-3 rounded border flex items-start justify-between" style={{ borderColor: 'var(--border-muted)' }}>
                <div>
                  <div className="font-medium" style={{ color: 'var(--text-primary)' }}>{c.title}</div>
                  <div className="text-sm mt-1" style={{ color: 'var(--text-muted)' }}>{c.reason}</div>
                  <div className="text-xs mt-1 font-mono" style={{ color: 'var(--text-muted)' }}>{c.id} · {c.priority} · {c.status}</div>
                </div>
                <div className="flex gap-2">{pathTag}</div>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// 入口 2: 情报 (Intel)
// ---------------------------------------------------------------------------

function IntelView() {
  return (
    <div className="space-y-4">
      <SectionTitle path="intel">情报流</SectionTitle>
      <div className="space-y-3">
        {MOCK_SIGNALS.map(s => (
          <div key={s.id} className="p-4 rounded-lg border" style={{ background: 'var(--bg-card)', borderColor: 'var(--border-muted)' }}>
            <div className="flex items-start justify-between">
              <div className="flex-1">
                <div className="font-medium" style={{ color: 'var(--text-primary)' }}>{s.summary}</div>
                <div className="text-sm mt-1" style={{ color: 'var(--text-muted)' }}>
                  发生时间: {s.occurred_at} · 规则版本: {s.admission_rule_version}
                </div>
              </div>
              <Badge color={s.confidence === 'verified' ? 'green' : s.confidence === 'likely' ? 'blue' : 'gray'}>{s.confidence}</Badge>
            </div>
            <div className="text-xs mt-2 font-mono" style={{ color: 'var(--text-muted)' }}>
              {s.id} → material:{s.material_id} → case: {MOCK_CASES.find(c => (c.related_signal_ids || []).includes(s.id))?.id || '-'}
            </div>
          </div>
        ))}
      </div>
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

  // T08: 真实数据接入 — 拉取 case 详情 (后端 case 行 = 单一权威, judgment/action/run 仍
  // 走 mock 占位, 等 T11/T13 批次替换); API 失败时保留 case_ (来自列表) 作为兜底。
  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    getCase(case_.id)
      .then((resp) => {
        if (cancelled) return;
        setLiveCase(resp.item);
        setUsingFallback(false);
      })
      .catch((e) => {
        if (cancelled) return;
        setError(e instanceof Error ? e.message : String(e));
        setLiveCase(null);
        setUsingFallback(true);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [case_.id]);

  const display = liveCase ?? case_;
  const judgments = MOCK_JUDGMENTS.filter(j => j.case_id === display.id);
  const actions = MOCK_ACTIONS.filter(a => a.case_id === display.id);
  const actionIds = actions.map(a => a.id);
  const runs = MOCK_RUNS.filter(r => actionIds.includes(r.action_id));
  const runIds = runs.map(r => r.id);
  const artifacts = MOCK_ARTIFACTS.filter(a => runIds.includes(a.run_id));

  // 走查 3 路径检测
  const hasMissingAssets = actions.length > 0 && artifacts.length === 0;
  const hasFailure = runs.some(r => r.status === 'failed');
  const hasPendingAcceptance = artifacts.some(a => a.status === 'verified');

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

      {/* 走查 3 路径指示器 */}
      <div className="p-3 rounded-lg border flex items-center gap-3" style={{ background: 'var(--bg-muted)', borderColor: 'var(--border-muted)' }}>
        <span className="text-sm font-medium" style={{ color: 'var(--text-primary)' }}>走查路径:</span>
        {hasMissingAssets && <Badge color="yellow">缺资产</Badge>}
        {hasPendingAcceptance && <Badge color="blue">待验收</Badge>}
        {hasFailure && <Badge color="red">失败</Badge>}
        {!hasMissingAssets && !hasPendingAcceptance && !hasFailure && <span className="text-sm" style={{ color: 'var(--text-muted)' }}>无异常</span>}
      </div>

      {/* 判断 */}
      <div className="p-4 rounded-lg border" style={{ background: 'var(--bg-card)', borderColor: 'var(--border-muted)' }}>
        <h3 className="font-semibold mb-3" style={{ color: 'var(--text-primary)' }}>判断 (Judgment)</h3>
        {judgments.length === 0 ? (
          <div className="text-sm" style={{ color: 'var(--text-muted)' }}>暂无判断</div>
        ) : (
          <div className="space-y-3">
            {judgments.map(j => (
              <div key={j.id} className="p-3 rounded border" style={{ borderColor: 'var(--border-muted)' }}>
                <div className="flex items-center gap-2 mb-2">
                  <Badge color={j.status === 'published' ? 'green' : 'yellow'}>{j.status}</Badge>
                  <span className="text-xs" style={{ color: 'var(--text-muted)' }}>{j.claim_type} · confidence: {j.confidence}</span>
                </div>
                <div className="text-sm" style={{ color: 'var(--text-primary)' }}>{j.claim}</div>
                {j.evidence_refs.length > 0 && (
                  <div className="text-xs mt-2" style={{ color: 'var(--text-muted)' }}>
                    证据: {j.evidence_refs.map(e => e.material_id).join(', ')}
                  </div>
                )}
              </div>
            ))}
          </div>
        )}
      </div>

      {/* 行动 + 运行 + 产物 */}
      <div className="p-4 rounded-lg border" style={{ background: 'var(--bg-card)', borderColor: 'var(--border-muted)' }}>
        <h3 className="font-semibold mb-3" style={{ color: 'var(--text-primary)' }}>行动 (Action) + 运行 (Run) + 产物 (Artifact)</h3>
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
                    <Badge color={a.status === 'succeeded' ? 'green' : a.status === 'failed' ? 'red' : a.status === 'running' ? 'blue' : 'gray'}>{a.status}</Badge>
                  </div>
                  <div className="text-xs font-mono mb-2" style={{ color: 'var(--text-muted)' }}>{a.id}</div>

                  {/* 运行 */}
                  {actionRuns.length > 0 && (
                    <div className="mb-3">
                      <div className="text-xs font-medium mb-1" style={{ color: 'var(--text-muted)' }}>运行:</div>
                      {actionRuns.map(r => (
                        <div key={r.id} className="flex items-center gap-2 text-xs">
                          <Badge color={r.status === 'succeeded' ? 'green' : r.status === 'failed' ? 'red' : 'gray'}>{r.status}</Badge>
                          <span style={{ color: 'var(--text-muted)' }}>{r.id}</span>
                          {r.error && <span style={{ color: 'var(--color-error)' }}>错误: {r.error.slice(0, 50)}</span>}
                        </div>
                      ))}
                    </div>
                  )}

                  {/* 产物 */}
                  {actionArtifacts.length > 0 ? (
                    <div>
                      <div className="text-xs font-medium mb-1" style={{ color: 'var(--text-muted)' }}>产物:</div>
                      <div className="space-y-1">
                        {actionArtifacts.map(art => (
                          <div key={art.id} className="flex items-center gap-2 text-xs">
                            <span style={{ color: 'var(--text-primary)' }}>{art.title}</span>
                            <Badge color={art.status === 'accepted' ? 'green' : art.status === 'verified' ? 'blue' : art.status === 'rejected' ? 'red' : 'gray'}>{art.status}</Badge>
                            <span style={{ color: 'var(--text-muted)' }}>{art.format} · {(art.size_bytes / 1024).toFixed(1)}KB</span>
                          </div>
                        ))}
                      </div>
                    </div>
                  ) : (
                    <div className="text-xs p-2 rounded" style={{ background: 'var(--bg-muted)', color: 'var(--text-muted)' }}>
                      缺资产: 此行动无产出产物
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
  return (
    <div className="space-y-4">
      <SectionTitle path="knowledge">经验库</SectionTitle>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {MOCK_KNOWLEDGE.map(k => (
          <div key={k.id} className="p-4 rounded-lg border" style={{ background: 'var(--bg-card)', borderColor: 'var(--border-muted)' }}>
            <div className="flex items-start justify-between">
              <div className="flex-1">
                <div className="font-medium" style={{ color: 'var(--text-primary)' }}>{k.title}</div>
                <div className="text-xs mt-1" style={{ color: 'var(--text-muted)' }}>{k.kind} · {k.status}</div>
              </div>
              <Badge color={k.status === 'published' ? 'green' : k.status === 'draft' ? 'yellow' : 'gray'}>{k.status}</Badge>
            </div>
            <div className="text-sm mt-2 line-clamp-3" style={{ color: 'var(--text-primary)' }}>{k.body}</div>
            <div className="text-xs mt-2 font-mono" style={{ color: 'var(--text-muted)' }}>
              {k.id} · reuse: {k.reuse_count}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// 主页面
// ---------------------------------------------------------------------------

export function V1Prototype() {
  const [tab, setTab] = useState<Tab>('workbench');
  const [selectedCase, setSelectedCase] = useState<Case | null>(null);

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
          {tab === 'workbench' && <WorkbenchView />}
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
