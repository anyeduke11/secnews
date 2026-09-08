/**
 * v1 四入口视图集 (v0.8.5 后不再是路由主体 — 三层 Sentinel 为唯一壳, spec = docs/v0.8.5/V0.8.5_PLAN.md)
 *
 * v0.8.5 C2: CaseDetail + Badge 提取至 './CaseDetail' (供 /cases/:caseId 深链复用),
 * 此处 re-export CaseDetail 保持旧测试 import 路径兼容。
 * 仍被引用的形态: KnowledgeV1Page (C4 挂 /knowledge/v1); WorkbenchPage/IntelPage/CasesPage
 * 不再被路由引用 (路由已重定向), 保留导出仅为测试与渐进迁移。
 *
 * 走查 3 路径 (CaseDetail 内显示):
 *   - 缺资产: Case 下有 Action 但无 Artifact
 *   - 待验收: Artifact status=pending/verified 等待 acceptance
 *   - 失败: Run status=failed 或 Action status=failed
 *
 * 数据: 全部走真实 API, 失败显 unavailable, 不再 mock fallback.
 */

import { useCallback, useEffect, useState } from 'react';
import type { Case } from '../../domain/v1_0';
import type { Knowledge } from '../../api/v1';
import {
  listCases, listKnowledge, getKnowledgeReuse, listSignals,
  adoptKnowledge, recordKnowledgeOutcome,
  publishKnowledge, deprecateKnowledge, retractKnowledge,
  type ReuseReceipt, type V1Signal, type ConditionDiff, type AdoptKnowledgeBody, type StateChangeBody,
} from '../../api/v1';
import { renderInlineMarkdown } from '../../lib/markdown';
import { useSSEWithRefetch } from './useSSEWithRefetch';
import { useToast } from '../Toast';
import { Badge, CaseDetail } from './CaseDetail';

// re-export: 旧测试 (c10_mutation_wiring / c11_aggregate_and_sse) 仍从 V1Prototype import
// CaseDetail — 被测对象已迁移至 './CaseDetail' (v0.8.5 C2), 语义不变。
export { CaseDetail };

// ---------------------------------------------------------------------------
// 类型 + 共享组件
// ---------------------------------------------------------------------------

export type V1Tab = 'workbench' | 'intel' | 'cases' | 'knowledge';

// ---------------------------------------------------------------------------
// 辅助组件
// ---------------------------------------------------------------------------

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

// ---------------------------------------------------------------------------
// 入口 4: 知识 (Knowledge)
// ---------------------------------------------------------------------------

function KnowledgeView() {
  // v1.0 T15.5 + C12: 接 listAll 真实数据 + 采用 UI + 失效 blocker 提示 + 生命周期按钮
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
  // F4b: 生命周期动作 loading 态
  const [lifecycleLoading, setLifecycleLoading] = useState<string | null>(null);
  const toast = useToast();

  const loadKnowledge = useCallback(async () => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    try {
      const r = await listKnowledge({ limit: 50 });
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
    } catch (e) {
      if (!cancelled) {
        setError(e instanceof Error ? e.message : String(e));
        setItems([]);
      }
    } finally {
      if (!cancelled) setLoading(false);
    }
    return () => { cancelled = true; };
  }, []);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      setLoading(true);
      setError(null);
      try {
        const r = await listKnowledge({ limit: 50 });
        if (cancelled) return;
        setItems(r.items);
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
      } catch (e) {
        if (!cancelled) {
          setError(e instanceof Error ? e.message : String(e));
          setItems([]);
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
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

  // F4b: 生命周期动作 (publish/deprecate/retract) — 走 allowed_actions 守卫
  const doLifecycle = async (kid: string, action: 'publish' | 'deprecate' | 'retract', base: StateChangeBody) => {
    setLifecycleLoading(kid + ':' + action);
    try {
      if (action === 'publish') await publishKnowledge(kid, base);
      else if (action === 'deprecate') await deprecateKnowledge(kid, { ...base, reason: '前端生命周期操作' });
      else await retractKnowledge(kid, { ...base, reason: '前端生命周期操作' });
      toast.show({ type: 'success', message: `${action} 成功` });
      await loadKnowledge();
    } catch (e) {
      toast.show({ type: 'error', message: `${action} 失败: ${e instanceof Error ? e.message : String(e)}` });
    } finally {
      setLifecycleLoading(null);
    }
  };

  const allowed = (k: Knowledge) => new Set(k.allowed_actions || []);

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
                {/* F4b: 生命周期按钮 (publish/deprecate/retract) — 基于 allowed_actions 守卫 */}
                {(allowed(k).has('publish') || allowed(k).has('deprecate') || allowed(k).has('retract')) && (
                  <div className="mt-3 pt-3 border-t flex flex-wrap gap-2" style={{ borderColor: 'var(--line)' }}>
                    {allowed(k).has('publish') && (
                      <button
                        onClick={() => doLifecycle(k.id, 'publish', { expected_revision: k.revision })}
                        disabled={lifecycleLoading === k.id + ':publish'}
                        className="px-3 py-1 text-xs rounded"
                        style={{ background: 'var(--mint)', color: 'var(--text-on-light)' }}
                      >
                        {lifecycleLoading === k.id + ':publish' ? '发布中…' : '发布'}
                      </button>
                    )}
                    {allowed(k).has('deprecate') && (
                      <button
                        onClick={() => doLifecycle(k.id, 'deprecate', { expected_revision: k.revision })}
                        disabled={lifecycleLoading === k.id + ':deprecate'}
                        className="px-3 py-1 text-xs rounded"
                        style={{ background: 'var(--color-warning)', color: 'var(--text-on-light)' }}
                      >
                        {lifecycleLoading === k.id + ':deprecate' ? '弃用中…' : '弃用'}
                      </button>
                    )}
                    {allowed(k).has('retract') && (
                      <button
                        onClick={() => doLifecycle(k.id, 'retract', { expected_revision: k.revision })}
                        disabled={lifecycleLoading === k.id + ':retract'}
                        className="px-3 py-1 text-xs rounded"
                        style={{ background: 'var(--color-error)', color: '#fff' }}
                      >
                        {lifecycleLoading === k.id + ':retract' ? '撤回中…' : '撤回'}
                      </button>
                    )}
                  </div>
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
