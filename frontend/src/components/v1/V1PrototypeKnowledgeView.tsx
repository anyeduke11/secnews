// V1PrototypeKnowledgeView — 从 V1Prototype.tsx 拆出的知识目录视图 (纯搬迁, 行为不变).
// 职责: 数据加载 / 采用表单状态 / 生命周期动作 / 列表渲染; 单条卡片见 V1PrototypeKnowledgeCard.

import { useCallback, useEffect, useState } from 'react';
import type { Knowledge } from '../../api/v1';
import {
  listKnowledge, getKnowledgeReuse,
  adoptKnowledge, recordKnowledgeOutcome,
  publishKnowledge, deprecateKnowledge, retractKnowledge,
  type ReuseReceipt, type ConditionDiff, type AdoptKnowledgeBody, type StateChangeBody,
} from '../../api/v1';
import { useToast } from '../../primitives/Toast';
import { SectionTitle } from './V1PrototypeParts';
import { KnowledgeCard } from './V1PrototypeKnowledgeCard';

// ---------------------------------------------------------------------------
// 知识 (Knowledge) — 目录 + 采用 + 生命周期 + 复查
// ---------------------------------------------------------------------------

export function KnowledgeView() {
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
          {items.map(k => (
            <KnowledgeCard
              key={k.id}
              k={k}
              receipt={receipts[k.id]}
              lifecycleLoading={lifecycleLoading}
              onLifecycle={doLifecycle}
              adoptOpenFor={adoptOpenFor}
              adoptCaseId={adoptCaseId}
              adoptDiff={adoptDiff}
              adoptSubmitting={adoptSubmitting}
              onAdoptOpenChange={setAdoptOpenFor}
              onAdoptCaseIdChange={setAdoptCaseId}
              onAdoptDiffChange={setAdoptDiff}
              onSubmitAdoption={submitAdoption}
              onRecordOutcome={recordOutcome}
              toast={toast}
            />
          ))}
        </div>
      )}
    </div>
  );
}