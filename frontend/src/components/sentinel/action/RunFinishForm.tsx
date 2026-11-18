/**
 * RunFinishForm — 第③段 Run「登记结果」人工回执表单 (B5 从 RunStage 抽出)
 *
 * 仅在 running 且该行表单展开时挂载 (由 RunActionRow 条件渲染), 因此 outcome / error
 * 的内部初始态即拆分前"打开表单重置为 done / 空"的语义; 失败真实性:
 * failed|timeout|needs_human 必须填原因码才可提交 (RA-9)。
 */
import { useState } from 'react';
import type { Run } from '../../../domain/v1_0';
import { btnGhostStyle, btnStyle, OUTCOME_OPTIONS, type FinishRunBody } from './runStageModel';

interface RunFinishFormProps {
  run: Run;
  busy: boolean;
  onFinish: (run: Run, body: FinishRunBody) => void;
  onClose: () => void;
}

export function RunFinishForm({ run, busy, onFinish, onClose }: RunFinishFormProps) {
  const [outcome, setOutcome] = useState('done');
  const [error, setError] = useState('');
  const needsError = outcome === 'failed' || outcome === 'timeout' || outcome === 'needs_human';

  return (
    <div
      data-testid="run-finish-form"
      style={{ width: '100%', display: 'grid', gap: 4, marginTop: 4, padding: 6, borderRadius: 6, background: 'var(--bg-hover, rgba(128,128,128,.08))' }}
    >
      <div style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
        <label style={{ color: 'var(--sn-ink-3)' }}>结果</label>
        <select
          data-testid="run-finish-outcome"
          value={outcome}
          onChange={e => setOutcome(e.target.value)}
          style={{ fontSize: 11 }}
        >
          {OUTCOME_OPTIONS.map(o => (
            <option key={o.value} value={o.value}>{o.label}</option>
          ))}
        </select>
      </div>
      {needsError && (
        <input
          data-testid="run-finish-error"
          placeholder="原因码 / 说明（失败真实性：必填）"
          value={error}
          onChange={e => setError(e.target.value)}
          style={{ fontSize: 11, padding: '3px 6px' }}
        />
      )}
      {outcome === 'done' && (
        <div style={{ color: 'var(--sn-ink-3)', fontSize: 10 }}>
          done 须先在第④段登记产物（RA-9：禁止成功但无产物）
        </div>
      )}
      <div style={{ display: 'flex', gap: 6 }}>
        <button
          type="button" data-testid="run-finish-submit"
          disabled={busy || (needsError && !error.trim())}
          style={btnStyle}
          onClick={() => {
            onFinish(run, {
              outcome,
              error: error.trim() || null,
              result_excerpt: null,
            });
            onClose();
          }}
        >
          {busy ? '登记中…' : '提交登记'}
        </button>
        <button type="button" style={btnGhostStyle} onClick={onClose}>
          取消
        </button>
      </div>
    </div>
  );
}
