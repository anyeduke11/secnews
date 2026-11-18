// V1PrototypeKnowledgeCard — 从 V1Prototype.tsx 拆出的知识条目卡 (纯搬迁, 行为不变).
// 职责: 单条知识卡片 (状态徽标 / blocker 提示 / 复用记录 / 生命周期按钮 / 采用表单).

import type { Knowledge } from '../../api/v1';
import {
  type ReuseReceipt, type ConditionDiff, type StateChangeBody,
} from '../../api/v1';
import { renderInlineMarkdown } from '../../lib/markdown';
import { useToast } from '../Toast';
import { Badge } from './CaseDetail';

const allowed = (k: Knowledge) => new Set(k.allowed_actions || []);

interface KnowledgeCardProps {
  k: Knowledge;
  receipt?: ReuseReceipt;
  lifecycleLoading: string | null;
  onLifecycle: (kid: string, action: 'publish' | 'deprecate' | 'retract', base: StateChangeBody) => void;
  adoptOpenFor: string | null;
  adoptCaseId: string;
  adoptDiff: ConditionDiff[];
  adoptSubmitting: boolean;
  onAdoptOpenChange: (id: string | null) => void;
  onAdoptCaseIdChange: (value: string) => void;
  onAdoptDiffChange: (diff: ConditionDiff[]) => void;
  onSubmitAdoption: (kid: string) => void;
  onRecordOutcome: (kid: string, caseId: string, outcome: 'success' | 'failure' | 'partial') => void;
  toast: ReturnType<typeof useToast>;
}

export function KnowledgeCard({
  k, receipt, lifecycleLoading, onLifecycle,
  adoptOpenFor, adoptCaseId, adoptDiff, adoptSubmitting,
  onAdoptOpenChange, onAdoptCaseIdChange, onAdoptDiffChange,
  onSubmitAdoption, onRecordOutcome, toast,
}: KnowledgeCardProps) {
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
              onClick={() => onLifecycle(k.id, 'publish', { expected_revision: k.revision })}
              disabled={lifecycleLoading === k.id + ':publish'}
              className="px-3 py-1 text-xs rounded"
              style={{ background: 'var(--mint)', color: 'var(--text-on-light)' }}
            >
              {lifecycleLoading === k.id + ':publish' ? '发布中…' : '发布'}
            </button>
          )}
          {allowed(k).has('deprecate') && (
            <button
              onClick={() => onLifecycle(k.id, 'deprecate', { expected_revision: k.revision })}
              disabled={lifecycleLoading === k.id + ':deprecate'}
              className="px-3 py-1 text-xs rounded"
              style={{ background: 'var(--color-warning)', color: 'var(--text-on-light)' }}
            >
              {lifecycleLoading === k.id + ':deprecate' ? '弃用中…' : '弃用'}
            </button>
          )}
          {allowed(k).has('retract') && (
            <button
              onClick={() => onLifecycle(k.id, 'retract', { expected_revision: k.revision })}
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
                onChange={(e) => onAdoptCaseIdChange(e.target.value)}
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
                    onAdoptDiffChange(v ? JSON.parse(v) : []);
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
                  onClick={() => onSubmitAdoption(k.id)}
                  disabled={adoptSubmitting}
                  className="px-3 py-1 text-xs rounded"
                  style={{ background: 'var(--mint)', color: 'var(--text-on-light)' }}
                >
                  {adoptSubmitting ? '采用中…' : '确认采用'}
                </button>
                <button
                  onClick={() => { onAdoptOpenChange(null); onAdoptCaseIdChange(''); onAdoptDiffChange([]); }}
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
                onClick={() => onAdoptOpenChange(k.id)}
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
                      if (c && c.length === 26) onRecordOutcome(k.id, c, 'success');
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
}