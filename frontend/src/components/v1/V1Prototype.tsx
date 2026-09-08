/**
 * V1Prototype — v1 知识目录视图 (v0.8.5 后唯一保留的 v1 页面形态).
 *
 * v0.8.5 D2 清理: WorkbenchView / IntelView / CasesView 与 WorkbenchPage / IntelPage /
 * CasesPage / V1Prototype 别名已删除 — 三层 Sentinel 为唯一壳 (spec = docs/v0.8.5/V0.8.5_PLAN.md),
 * 对应能力已由 SignalPanel / CaseQueuePanel / ExecOverviewPanel 三区块 + /cases/:caseId 深链承接。
 * 本文件仅承载:
 *   - KnowledgeView  → /knowledge/v1 (KnowledgeV1Page, 知识目录 + 采用/生命周期)
 *   - CaseDetail/Badge → './CaseDetail' re-export (旧测试 import 路径兼容)
 *
 * 数据: 全部走真实 API, 失败显 unavailable, 不再 mock fallback.
 */

import { useCallback, useEffect, useState } from 'react';
import type { Knowledge } from '../../api/v1';
import {
  listKnowledge, getKnowledgeReuse,
  adoptKnowledge, recordKnowledgeOutcome,
  publishKnowledge, deprecateKnowledge, retractKnowledge,
  type ReuseReceipt, type ConditionDiff, type AdoptKnowledgeBody, type StateChangeBody,
} from '../../api/v1';
import { renderInlineMarkdown } from '../../lib/markdown';
import { useSSEWithRefetch } from './useSSEWithRefetch';
import { useToast } from '../Toast';
import { Badge } from './CaseDetail';

// ---------------------------------------------------------------------------
// 共享组件
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
// 知识 (Knowledge) — 目录 + 采用 + 生命周期 + 复查
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
          暂无经验库条目 (行动层复盘产出知识后此处出现)
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
// 页面: /knowledge/v1 (更多 → 知识库 → v1 目录)
// ---------------------------------------------------------------------------

export function KnowledgeV1Page() {
  // T17.5: v1_* 事件 → toast (fire-and-forget)
  void useSSEWithRefetch(() => {});
  return (
    <div className="max-w-6xl mx-auto p-6">
      <KnowledgeView />

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
